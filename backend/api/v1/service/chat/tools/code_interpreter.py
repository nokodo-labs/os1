"""code interpreter tool - execute Python code in E2B sandbox.

runs user code in a sandboxed E2B environment with session
persistence across the conversation thread. the sandbox id
is stored in tool message metadata so subsequent calls can
reconnect to the same environment.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.e2b import E2BClient, FileEntry
from api.models.file import File, FileSource
from api.settings import settings
from api.v1.service.chat.context import AppContext
from api.v1.service.files import read_content, store_file
from api.v1.service.projects import resolve_thread_project_id
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import FileContent, ImageContent, ToolMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_METADATA_SANDBOX_KEY = "e2b_sandbox_id"
_MAX_OUTPUT_CHARS = 500_000
_TRUNCATION_LINES = 50


class CodeInterpreterInput(BaseModel):
	"""input schema for code_interpreter tool."""

	model_config = ConfigDict(extra="forbid")

	action_name: str = Field(
		...,
		description=(
			"a short verb phrase describing what this run does "
			"(e.g. 'analyzing dataset', 'generating chart')."
		),
	)
	code: str = Field(
		...,
		description="the Python code to execute in the sandbox.",
	)
	file_ids: list[str] = Field(
		default_factory=list,
		description=(
			"list of file IDs to upload into the sandbox before "
			"execution. files will be placed in /home/user/."
		),
	)


def _find_sandbox_id(thread: SDKThread) -> str | None:
	"""find the most recent E2B sandbox id from tool message metadata."""
	for msg in reversed(thread.messages):
		if msg.role != "tool":
			continue
		if msg.metadata and _METADATA_SANDBOX_KEY in msg.metadata:
			value = msg.metadata[_METADATA_SANDBOX_KEY]
			if isinstance(value, str):
				return value
	return None


def _truncate_field(text: str, *, max_lines: int = _TRUNCATION_LINES) -> str:
	"""truncate text keeping the first and last N lines."""
	lines = text.splitlines()
	total = len(lines)
	if total <= max_lines * 2:
		return text
	head = lines[:max_lines]
	tail = lines[-max_lines:]
	omitted = total - max_lines * 2
	return "\n".join(head + [f"... ({omitted} lines omitted) ..."] + tail)


async def _store_output_files(
	inline_images: list[FileEntry],
	files: list[FileEntry],
	*,
	session: AsyncSession,
	owner_id: TypeID,
	project_id: str | None = None,
	agent_id: str | None = None,
	thread_id: str | None = None,
) -> list[ImageContent | FileContent]:
	"""persist E2B output files and return tool attachments.

	inline_images (from execution results, e.g. matplotlib) become
	ImageContent so the frontend renders them as image previews.
	all other files (including image files from disk) become
	FileContent so the frontend renders them as file widgets.
	"""
	attachments: list[ImageContent | FileContent] = []

	async def _store(
		entry: FileEntry, *, as_image: bool
	) -> ImageContent | FileContent | None:
		try:
			stored = await store_file(
				session,
				data=entry.content,
				owner_id=owner_id,
				filename=entry.filename,
				content_type=entry.mime_type,
				source=FileSource.GENERATED,
				project_id=project_id,
			)
			file_meta: JSONObject = {}
			if agent_id:
				file_meta["agent_id"] = agent_id
			if thread_id:
				file_meta["thread_id"] = thread_id
			if file_meta and hasattr(stored, "metadata_"):
				stored.metadata_ = {**(stored.metadata_ or {}), **file_meta}
				await session.flush()
			file_url = f"/v1/files/{stored.id}/content"
			if as_image:
				return ImageContent(
					url=file_url,
					filename=entry.filename,
					media_type=entry.mime_type,
					metadata={"file_id": str(stored.id)},
				)
			return FileContent(
				url=file_url,
				filename=entry.filename,
				media_type=entry.mime_type,
				metadata={"file_id": str(stored.id)},
			)
		except Exception:
			logger.warning(
				"failed to store output file %s", entry.filename, exc_info=True
			)
			return None

	for entry in inline_images:
		result = await _store(entry, as_image=True)
		if result:
			attachments.append(result)
	for entry in files:
		result = await _store(entry, as_image=False)
		if result:
			attachments.append(result)
	return attachments


async def _upload_input_files(
	client: E2BClient,
	file_ids: list[str],
	*,
	session: AsyncSession,
) -> list[str]:
	"""download files from storage and upload them to the sandbox.

	returns list of filenames that were successfully uploaded.
	"""
	uploaded: list[str] = []
	for file_id in file_ids:
		result = await session.execute(
			select(File).where(File.id == file_id, File.deleted_at.is_(None))
		)
		file = result.scalars().one_or_none()
		if file is None:
			logger.warning("code_interpreter: input file %s not found", file_id)
			continue
		try:
			stream, _, _ = await read_content(file)
			chunks: list[bytes] = []
			async for chunk in stream:
				chunks.append(chunk)
			raw = b"".join(chunks)
			filename = file.filename or file_id
			await client.upload_file(f"/home/user/{filename}", raw)
			uploaded.append(filename)
		except Exception:
			logger.warning(
				"code_interpreter: failed to upload file %s",
				file_id,
				exc_info=True,
			)
	return uploaded


def _compute_tool_description() -> str:
	desc = (
		"execute Python code in a sandboxed notebook to perform "
		"calculations, data analysis, file operations, or any "
		"programmatic task. the environment persists across the "
		"conversation, so you can build and iterate. "
		"to attach outputs (files, charts, reports, etc.) to the chat, "
		"always save them to /home.\n\n"
	)
	packages = settings.code_interpreter.e2b.available_packages
	if packages:
		desc += "pre-installed packages: " + ", ".join(packages)
	return desc


class CodeInterpreterTool(Tool[AppContext]):
	"""execute Python code in a sandboxed notebook environment."""

	name: str = Field(default="code_interpreter")
	description: str = Field(
		default_factory=_compute_tool_description,
	)
	parameters: JSONObject = Field(
		default_factory=(lambda: CodeInterpreterInput.model_json_schema()),
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)

		ci_settings = settings.code_interpreter
		if not ci_settings.enabled:
			return self.error(
				"code interpreter is not enabled",
				__agent_context__,
			)

		if not ci_settings.e2b.api_key:
			return self.error(
				"code interpreter is not configured",
				__agent_context__,
			)

		inp = CodeInterpreterInput.model_validate(kwargs)

		# find existing sandbox from thread history
		sandbox_id = _find_sandbox_id(__agent_context__.thread)

		client = E2BClient(
			api_key=ci_settings.e2b.api_key,
			template=ci_settings.e2b.template,
		)

		try:
			await client.connect(sandbox_id)

			# upload requested files into the sandbox
			if inp.file_ids:
				await _upload_input_files(
					client,
					inp.file_ids,
					session=__app_context__.session,
				)

			result = await client.run_code(inp.code, timeout=ci_settings.timeout)
		except Exception:
			logger.exception("code interpreter execution failed")
			return self.error(
				"code interpreter execution failed. please try again.",
				__agent_context__,
			)
		finally:
			try:
				await client.pause()
			except Exception:
				logger.debug("failed to pause sandbox", exc_info=True)

		# build response
		response: dict[str, object] = {
			"action": inp.action_name,
		}
		if result.stdout:
			response["stdout"] = _truncate_field(result.stdout)
		if result.stderr:
			response["stderr"] = _truncate_field(result.stderr)
		if result.results:
			response["results"] = result.results
		if result.error:
			response["error"] = result.error

		output = json.dumps(response, ensure_ascii=False)

		# final safety cap on total JSON size
		if len(output) > _MAX_OUTPUT_CHARS:
			if "stdout" in response:
				response["stdout"] = _truncate_field(
					str(response["stdout"]), max_lines=20
				)
			if "stderr" in response:
				response["stderr"] = _truncate_field(
					str(response["stderr"]), max_lines=20
				)
			output = json.dumps(response, ensure_ascii=False)

		# persist output files and build attachments
		thread_project_id: str | None = None
		if __app_context__.thread_id:
			thread_project_id = await resolve_thread_project_id(
				__app_context__.thread_id, __app_context__.session
			)

		agent_id = str(__app_context__.agent_id) if __app_context__.agent_id else None
		thread_id = (
			str(__app_context__.thread_id) if __app_context__.thread_id else None
		)

		attachments = await _store_output_files(
			result.inline_images,
			result.files,
			session=__app_context__.session,
			owner_id=__app_context__.user_id,
			project_id=thread_project_id,
			agent_id=agent_id,
			thread_id=thread_id,
		)

		# build metadata with sandbox id for session persistence
		metadata: JSONObject = {
			**(__agent_context__.metadata or {}),
		}
		if result.sandbox_id:
			metadata[_METADATA_SANDBOX_KEY] = result.sandbox_id

		return ToolMessage(
			tool_call_id=__agent_context__.tool_call_id,
			tool_output=output,
			metadata=metadata,
			is_error=bool(result.error),
			attachments=attachments,
		)
