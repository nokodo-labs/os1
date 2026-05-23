"""files tools - get/list and edit file metadata."""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.file import FileUpdate
from api.schemas.search import SearchMode, SearchParams
from api.v1.service import files as file_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)
_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)


class FileGetInput(BaseModel):
	"""input schema for file_get tool.

	provide file_id to fetch a specific file, or omit to list recent files.
	"""

	model_config = ConfigDict(extra="forbid")

	file_id: TypeID | None = Field(
		default=None,
		description=(
			"ID of a specific file to fetch. when omitted, lists recent files instead."
		),
	)
	query: str | None = Field(
		default=None,
		description=(
			"hybrid search query. when provided and file_id is omitted, searches files."
		),
		min_length=1,
		max_length=500,
	)
	cursor: str | None = Field(
		default=None,
		description="cursor returned by a previous file search page.",
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
			"retrieve files. provide file_id to get metadata for a specific file, "
			"or omit to list the user's most recent uploads."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: FileGetInput.model_json_schema()
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

		if inp.file_id:
			# direct fetch by ID
			try:
				f = await file_service.get_file(
					inp.file_id,
					__app_context__.session,
					principal=__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
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
			return self.success(json.dumps(result), __tool_call_context__)

		if inp.query:
			try:
				page = await file_service.search_files(
					inp.query,
					__app_context__.session,
					principal=__app_context__.principal,
					limit=inp.limit,
					cursor=inp.cursor,
					search_params=_HYBRID_SEARCH,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __tool_call_context__)
			results = [item.model_dump(mode="json") for item in page.items]
			out = {
				"status": "success",
				"message": f"found {len(results)} files",
				"count": len(results),
				"results": results,
				"next_cursor": page.next_cursor,
				"has_more": page.has_more,
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
