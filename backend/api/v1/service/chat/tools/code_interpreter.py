"""code interpreter tool - execute Python code in E2B sandbox.

runs user code in a sandboxed E2B environment with session
persistence across the conversation thread. the sandbox id
is stored in tool message metadata so subsequent calls can
reconnect to the same environment.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.e2b import E2BClient, FileEntry
from api.models.file import FileSource
from api.settings import settings
from api.v1.service.chat.context import AppContext
from api.v1.service.files import store_file
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import FileContent, ImageContent, ToolMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)

_METADATA_SANDBOX_KEY = "e2b_sandbox_id"
_MAX_OUTPUT_CHARS = 500_000
_TRUNCATION_LINES = 50


class CodeInterpreterInput(BaseModel):
	"""input schema for code_interpreter tool."""

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


_IMAGE_EXTENSIONS = frozenset({"png", "jpeg", "jpg", "svg", "gif", "webp"})


async def _store_output_files(
	files: list[FileEntry],
	*,
	session: AsyncSession,
	owner_id: str,
) -> list[ImageContent | FileContent]:
	"""persist E2B output files and return tool attachments."""
	attachments: list[ImageContent | FileContent] = []
	for entry in files:
		try:
			stored = await store_file(
				session,
				data=entry.content,
				owner_id=owner_id,
				filename=entry.filename,
				content_type=entry.mime_type,
				source=FileSource.GENERATED,
			)
			file_url = f"/v1/files/{stored.id}/content"
			ext = (
				entry.filename.rsplit(".", 1)[-1].lower()
				if "." in entry.filename
				else ""
			)
			if ext in _IMAGE_EXTENSIONS:
				attachments.append(
					ImageContent(
						url=file_url,
						filename=entry.filename,
						media_type=entry.mime_type,
						metadata={"file_id": str(stored.id)},
					)
				)
			else:
				attachments.append(
					FileContent(
						url=file_url,
						filename=entry.filename,
						media_type=entry.mime_type,
						metadata={"file_id": str(stored.id)},
					)
				)
		except Exception:
			logger.warning(
				"failed to store output file %s", entry.filename, exc_info=True
			)
	return attachments


class CodeInterpreterTool(Tool[AppContext]):
	"""execute Python code in a sandboxed notebook environment."""

	name: str = Field(default="code_interpreter")
	description: str = Field(
		default=(
			"execute Python code in a sandboxed notebook to perform "
			"calculations, data analysis, file operations, or any "
			"programmatic task. the environment persists across the "
			"conversation, so you can build and iterate."
		),
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
		attachments = await _store_output_files(
			result.files,
			session=__app_context__.session,
			owner_id=str(__app_context__.user_id),
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
