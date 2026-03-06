"""files tools - get/list and edit file metadata."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from api.schemas.file import FileUpdate
from api.v1.service import files as file_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class FileGetInput(BaseModel):
	"""input schema for file_get tool.

	provide file_id to fetch a specific file, or omit to list recent files.
	"""

	file_id: str | None = Field(
		default=None,
		description=(
			"ID of a specific file to fetch. when omitted, lists recent files instead."
		),
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

	file_id: str = Field(..., description="ID of the file to rename")
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
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = FileGetInput.model_validate(kwargs)

		if inp.file_id:
			# direct fetch by ID
			try:
				f = await file_service.get_file(
					TypeID(inp.file_id),
					__app_context__.session,
					principal=__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			parts = [f"filename: {f.filename or '(unnamed)'}"]
			if f.mime_type:
				parts.append(f"mime type: {f.mime_type}")
			if f.size_bytes is not None:
				parts.append(f"size: {f.size_bytes} bytes")
			parts.append(f"status: {f.status.value}")
			parts.append(f"source: {f.source.value}")
			parts.append(f"created: {f.created_at.isoformat()}")
			return self.success("\n".join(parts), __agent_context__)

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
			return self.error(str(exc.detail), __agent_context__)

		if not files:
			return self.success("no files found", __agent_context__)

		lines = []
		for f in files:
			size = f" ({f.size_bytes} bytes)" if f.size_bytes else ""
			mime = f" [{f.mime_type}]" if f.mime_type else ""
			lines.append(f"- [{f.id}] {f.filename or '(unnamed)'}{mime}{size}")
		return self.success("\n".join(lines), __agent_context__)


class FileEditTool(Tool[AppContext]):
	"""rename an existing file."""

	name: str = Field(default="file_edit")
	description: str = Field(default="update the display filename of an existing file")
	parameters: JSONObject = Field(
		default_factory=lambda: FileEditInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = FileEditInput.model_validate(kwargs)
		try:
			f = await file_service.update_file(
				TypeID(inp.file_id),
				FileUpdate(filename=inp.filename),
				__app_context__.session,
				principal=__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)

		return self.success(
			f"file updated: [{f.id}] {f.filename or '(unnamed)'}",
			__agent_context__,
		)
