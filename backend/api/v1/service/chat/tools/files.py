"""files tools - get/list and edit file metadata."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.models.file import File
from api.schemas.file import FileUpdate
from api.schemas.search import Page, SearchMode, SearchParams
from api.v1.service import files as file_service
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.models import fetch_agent_input_modalities
from api.v1.service.files.modalities import (
	classify_media,
	modality_supported,
)
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import FileContent, ImageContent, ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)
_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)

# max files a single file_get call may fetch natively in one batch. fetching
# them together lands all needed media on one tool message in one turn.
MAX_FILE_GET_BATCH = 8


def _file_search_result(f: File) -> dict[str, object]:
	"""summarize a file for agent search results."""
	return {
		"id": str(f.id),
		"filename": f.filename or "(unnamed)",
		"mime_type": f.mime_type or "",
		"size_bytes": f.size_bytes,
		**({"preview": f.description[:100]} if f.description else {}),
	}


class FileGetInput(BaseModel):
	"""input schema for file_get tool.

	provide file_ids to fetch specific files, or omit to list/search files.
	"""

	model_config = ConfigDict(extra="forbid")

	file_ids: list[TypeID] | None = Field(
		default=None,
		description=(
			"IDs of specific files to fetch (up to 8 per call). fetch every file "
			"you need together so they all land on one message. when omitted, "
			"lists or searches files instead."
		),
		max_length=MAX_FILE_GET_BATCH,
	)
	query: str | None = Field(
		default=None,
		description=(
			"hybrid search query. when provided and file_ids is omitted, "
			"searches files."
		),
		min_length=1,
		max_length=500,
	)
	offset: int = Field(
		default=0,
		description="number of file search results to skip before this page.",
		ge=0,
	)
	limit: int = Field(
		default=10,
		description="max files to return when listing (ignored for direct fetch)",
		ge=1,
		le=50,
	)
	sort_by: Literal["created_at", "updated_at", "filename", "size_bytes"] = Field(
		default="created_at",
		description="sort field when listing",
	)
	sort_dir: Literal["asc", "desc"] = Field(
		default="desc",
		description="sort direction when listing",
	)


class FileEditInput(BaseModel):
	"""input schema for editing file metadata."""

	model_config = ConfigDict(extra="forbid")

	file_id: TypeID = Field(..., description="ID of the file to rename")
	filename: str | None = Field(
		default=None,
		description="new display filename",
		min_length=1,
		max_length=255,
	)


class FileGetTool(Tool[AppContext]):
	"""list recent files or fetch a specific file by ID."""

	name: str = Field(default="file_get")
	description: str = Field(
		default=(
			"retrieve files. provide file_ids to fetch specific files (up to 8 "
			"at once), or omit to list the user's most recent uploads."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: FileGetInput.model_json_schema()
	)

	async def _fetch_batch(
		self,
		file_ids: list[TypeID],
		app_context: AppContext,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""fetch one or more files, attaching supported media natively.

		all fetched media lands on this single tool message so it shares one
		protection turn. unsupported modalities return metadata only.
		"""
		supported: set[str] | None = None
		modalities_loaded = False
		results: list[dict[str, object]] = []
		attachments: list[ImageContent | FileContent] = []
		for file_id in file_ids:
			try:
				f = await file_service.get_file(
					file_id,
					app_context.session,
					principal=app_context.principal,
				)
			except HTTPException as exc:
				results.append(
					{"status": "error", "id": str(file_id), "message": str(exc.detail)}
				)
				continue
			result: dict[str, object] = {
				"status": "success",
				"message": "file retrieved",
				"id": str(f.id),
				"filename": f.filename or "(unnamed)",
				"file_status": f.status.value,
				"source": f.source.value,
				"created_at": f.created_at.isoformat(),
			}
			if f.mime_type:
				result["mime_type"] = f.mime_type
			if f.size_bytes is not None:
				result["size_bytes"] = f.size_bytes

			# media files attach natively when the model supports the modality;
			# otherwise metadata only. native bytes are hydrated later by the
			# file_resolve filter. the updated_at stamp lets the projection layer
			# tell distinct renditions of a mutable file apart.
			mime = f.mime_type or ""
			category = classify_media(mime)
			if category in ("image", "audio", "video"):
				if not modalities_loaded:
					supported = await fetch_agent_input_modalities(
						app_context.agent_id, app_context.session
					)
					modalities_loaded = True
				if modality_supported(mime, supported):
					metadata: JSONObject = {
						"file_id": str(f.id),
						"fetched": True,
						"updated_at": f.updated_at.isoformat(),
					}
					attachment = (
						ImageContent(
							filename=f.filename,
							media_type=mime,
							metadata=metadata,
						)
						if category == "image"
						else FileContent(
							filename=f.filename,
							media_type=mime,
							metadata=metadata,
						)
					)
					attachments.append(attachment)
					result["message"] = "file retrieved and attached to this message"
				else:
					result["message"] = (
						"file retrieved; this model cannot view this media type "
						"natively"
					)
			results.append(result)

		output = {
			"status": "success",
			"count": len(results),
			"results": results,
		}
		return ToolMessage(
			tool_call_id=tool_call_context.tool_call_id,
			tool_output=json.dumps(output),
			metadata=tool_call_context.metadata,
			is_error=False,
			attachments=attachments,
		)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = FileGetInput.model_validate(kwargs)

		if inp.file_ids:
			return await self._fetch_batch(
				inp.file_ids, __app_context__, __tool_call_context__
			)

		if inp.query:
			try:
				scored = await file_service.search_files(
					inp.query,
					__app_context__.session,
					principal=__app_context__.principal,
					limit=inp.limit + 1,
					offset=inp.offset,
					search_params=_HYBRID_SEARCH,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
			page = Page(
				items=[hit.item for hit in scored[: inp.limit]],
				has_more=len(scored) > inp.limit,
			)
			results = [_file_search_result(f) for f in page.items]
			next_offset = inp.offset + inp.limit if page.has_more else None
			out = {
				"status": "success",
				"message": f"found {len(results)} files",
				"count": len(results),
				"results": results,
				"next_offset": next_offset,
			}
			return self.success(json.dumps(out), __tool_call_context__)

		# list recent files
		try:
			files = await file_service.list_files(
				__app_context__.session,
				principal=__app_context__.principal,
				limit=inp.limit,
				sort_by=inp.sort_by,
				sort_dir=inp.sort_dir,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)

		if not files:
			out = {
				"status": "success",
				"message": "no files found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __tool_call_context__)

		results = [
			{
				"id": str(f.id),
				"filename": f.filename or "(unnamed)",
				"mime_type": f.mime_type or "",
				"size_bytes": f.size_bytes,
			}
			for f in files
		]
		n = len(results)
		msg = f"found {n} {'file' if n == 1 else 'files'}"
		out = {"status": "success", "message": msg, "count": n, "results": results}
		return self.success(json.dumps(out), __tool_call_context__)


class FileEditTool(Tool[AppContext]):
	"""rename an existing file."""

	name: str = Field(default="file_edit")
	description: str = Field(default="update the display filename of an existing file")
	parameters: JSONObject = Field(
		default_factory=lambda: FileEditInput.model_json_schema()
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		inp = FileEditInput.model_validate(kwargs)
		try:
			f = await file_service.update_file(
				inp.file_id,
				FileUpdate(filename=inp.filename),
				__app_context__.session,
				principal=__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)

		out = {"status": "success", "message": "file updated", "id": str(f.id)}
		return self.success(json.dumps(out), __tool_call_context__)
