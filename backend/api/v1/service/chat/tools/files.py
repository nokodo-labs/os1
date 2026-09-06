"""files tools - get/list and edit file metadata."""

import json
import logging
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.models.file import File
from api.schemas.file import FileUpdate
from api.schemas.message import CitationSource
from api.schemas.search import Page, SearchMode, SearchParams
from api.v1.service.chat.citation_sources import (
	CitableSource,
	citation_source,
	with_citable_sources,
)
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.models import fetch_agent_input_modalities
from api.v1.service.chat.tools.base import Tool
from api.v1.service.files import (
	get_file,
	list_files,
	query_file_content,
	read_file_content_lines,
	search_files,
	update_file,
)
from api.v1.service.files.modalities import (
	classify_media,
	modality_supported,
)
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import FileContent, ImageContent, ToolMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)
_HYBRID_SEARCH = SearchParams(mode=SearchMode.HYBRID)

MAX_FILE_GET_BATCH = 8
"max files a single file_get call may fetch natively in one batch"


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
			"hybrid search query. with exactly one file_id, searches inside that "
			"file's content and returns the top matching chunks with their line "
			"ranges. with no file_ids, searches across files."
		),
		min_length=1,
		max_length=500,
	)
	line_start: int | None = Field(
		default=None,
		ge=1,
		description=(
			"with exactly one file_id, read that file's extracted text starting "
			"at this 1-based line. selects line-read mode."
		),
	)
	line_end: int | None = Field(
		default=None,
		ge=1,
		description=(
			"last 1-based line to read, inclusive. omit to read to the end of the file."
		),
	)
	include_media: bool = Field(
		default=True,
		description=(
			"when fetching files by id, attach supported image/audio/video bytes "
			"for native viewing. set false for metadata and text description only."
		),
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


class FileGetTool(Tool):
	"""list recent files or fetch a specific file by ID."""

	name: str = Field(default="file_get")
	description: str = Field(
		default=(
			"retrieve files and their contents. with a single file_id, set "
			"line_start to read the file's text by line range, or set query to "
			"search inside that file and get the top matching passages with their "
			"line ranges. with multiple file_ids, fetch the files (media is "
			"attached for native viewing; documents return their text "
			"description). with no file_ids, set query to search files or omit it "
			"to list the most recent uploads."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: FileGetInput.model_json_schema()
	)

	async def _fetch_batch(
		self,
		file_ids: list[TypeID],
		include_media: bool,
		app_context: AppContext,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""fetch one or more files, attaching supported media natively.

		all fetched media lands on this single tool message so it shares one
		protection turn. when include_media is false, or the model cannot view
		the modality, files return metadata and their text description only.
		"""
		supported: set[str] | None = None
		modalities_loaded = False
		results: list[dict[str, object]] = []
		attachments: list[ImageContent | FileContent] = []
		citable_sources: list[CitableSource] = []
		for file_id in file_ids:
			try:
				f = await get_file(
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
			if f.description:
				result["description"] = f.description
			citable_sources.append(
				citation_source(CitationSource.FILE, f.id, f.filename)
			)

			# media files attach natively when requested and the model supports
			# the modality; otherwise metadata + description only. native bytes
			# are hydrated later by the file_resolve filter. the updated_at stamp
			# lets the projection layer tell distinct renditions of a mutable
			# file apart.
			mime = f.mime_type or ""
			category = classify_media(mime)
			if category in ("image", "audio", "video"):
				if not include_media:
					result["message"] = (
						"file retrieved; media bytes omitted, description only"
					)
				else:
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
						result["message"] = (
							"file retrieved and attached to this message"
						)
					else:
						result["message"] = (
							"file retrieved; this model cannot view this media "
							"type natively"
						)
			results.append(result)

		output = {
			"status": "success",
			"count": len(results),
			"results": results,
		}
		return self.success(
			json.dumps(output),
			tool_call_context,
			metadata=with_citable_sources(None, citable_sources),
			attachments=attachments,
		)

	async def _query_content(
		self,
		file_id: TypeID,
		query: str,
		limit: int,
		app_context: AppContext,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""search inside one file's body text and return the top passages."""
		try:
			hits = await query_file_content(
				file_id,
				query,
				app_context.session,
				principal=app_context.principal,
				limit=limit,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		results = [
			{
				"text": hit.text,
				"score": round(hit.score, 4),
				"chunk_index": hit.chunk_index,
				"chunk_count": hit.chunk_count,
				"line_start": hit.line_start,
				"line_end": hit.line_end,
			}
			for hit in hits
		]
		out: dict[str, object] = {
			"status": "success",
			"message": (
				f"found {len(results)} matching passages"
				if results
				else "no matching content found in this file"
			),
			"count": len(results),
			"file_id": str(file_id),
			"results": results,
		}
		return self.success(
			json.dumps(out),
			tool_call_context,
			metadata=with_citable_sources(
				None,
				[citation_source(CitationSource.FILE, file_id, None)],
			),
		)

	async def _read_lines(
		self,
		file_id: TypeID,
		line_start: int,
		line_end: int | None,
		app_context: AppContext,
		tool_call_context: ToolCallContext,
	) -> ToolMessage:
		"""read a line range of one file's extracted text."""
		try:
			lines = await read_file_content_lines(
				file_id,
				app_context.session,
				principal=app_context.principal,
				line_start=line_start,
				line_end=line_end,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), tool_call_context)
		out: dict[str, object]
		if lines.total_lines == 0:
			out = {
				"status": "success",
				"message": "this file has no readable text content",
				"file_id": str(file_id),
				"total_lines": 0,
				"text": "",
			}
			return self.success(
				json.dumps(out),
				tool_call_context,
				metadata=with_citable_sources(
					None,
					[citation_source(CitationSource.FILE, file_id, None)],
				),
			)
		out = {
			"status": "success",
			"message": (
				f"read lines {lines.line_start}-{lines.line_end} of {lines.total_lines}"
			),
			"file_id": str(file_id),
			"line_start": lines.line_start,
			"line_end": lines.line_end,
			"total_lines": lines.total_lines,
			"text": lines.text,
		}
		return self.success(
			json.dumps(out),
			tool_call_context,
			metadata=with_citable_sources(
				None,
				[citation_source(CitationSource.FILE, file_id, None)],
			),
		)

	async def run(
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

		# line-read mode: one file's extracted text addressed by line range.
		if inp.line_start is not None:
			if not inp.file_ids or len(inp.file_ids) != 1:
				return self.error(
					"reading by line requires exactly one file_id",
					__tool_call_context__,
				)
			return await self._read_lines(
				inp.file_ids[0],
				inp.line_start,
				inp.line_end,
				__app_context__,
				__tool_call_context__,
			)

		# content-query mode: search inside one file's body text.
		if inp.file_ids and inp.query:
			if len(inp.file_ids) != 1:
				return self.error(
					"querying file content requires exactly one file_id",
					__tool_call_context__,
				)
			return await self._query_content(
				inp.file_ids[0],
				inp.query,
				inp.limit,
				__app_context__,
				__tool_call_context__,
			)

		if inp.file_ids:
			return await self._fetch_batch(
				inp.file_ids,
				inp.include_media,
				__app_context__,
				__tool_call_context__,
			)

		if inp.query:
			try:
				scored = await search_files(
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
			out: dict[str, object] = {
				"status": "success",
				"message": f"found {len(results)} files",
				"count": len(results),
				"results": results,
				"next_offset": next_offset,
			}
			return self.success(
				json.dumps(out),
				__tool_call_context__,
				metadata=with_citable_sources(
					None,
					[
						citation_source(CitationSource.FILE, f.id, f.filename)
						for f in page.items
					],
				),
			)

		# list recent files
		try:
			files = await list_files(
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
		list_out: dict[str, object] = {
			"status": "success",
			"message": msg,
			"count": n,
			"results": results,
		}
		return self.success(
			json.dumps(list_out),
			__tool_call_context__,
			metadata=with_citable_sources(
				None,
				[citation_source(CitationSource.FILE, f.id, f.filename) for f in files],
			),
		)


class FileEditTool(Tool):
	"""rename an existing file."""

	name: str = Field(default="file_edit")
	description: str = Field(default="update the display filename of an existing file")
	parameters: JSONObject = Field(
		default_factory=lambda: FileEditInput.model_json_schema()
	)

	async def run(
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
			f = await update_file(
				inp.file_id,
				FileUpdate(filename=inp.filename),
				__app_context__.session,
				principal=__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)

		out = {"status": "success", "message": "file updated", "id": str(f.id)}
		return self.success(json.dumps(out), __tool_call_context__)
