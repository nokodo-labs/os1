"""notes tools - get/search and create/edit notes."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.schemas.note import NoteCreate, NoteUpdate
from api.v1.service import notes as note_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class NoteGetInput(BaseModel):
	"""input schema for note_get tool.

	provide note_id to fetch a specific note, or query to search.
	"""

	model_config = ConfigDict(extra="forbid")

	note_id: str | None = Field(
		default=None,
		description="ID of a specific note to fetch. when provided, query is ignored.",
	)
	query: str | None = Field(
		default=None,
		description=(
			"natural language search query. required when note_id is not given. "
			"hybrid BM25 + semantic search is used."
		),
	)
	limit: int = Field(
		default=5,
		description="max notes to return when searching (ignored for direct fetch)",
		ge=1,
		le=20,
	)


class NoteWriteInput(BaseModel):
	"""input schema for note_write tool.

	provide note_id to update an existing note, or omit to create a new one.
	"""

	model_config = ConfigDict(extra="forbid")

	note_id: str | None = Field(
		default=None,
		description="ID of the note to edit. omit to create a new note.",
	)
	title: str | None = Field(
		default=None,
		description="title of the note. required when creating.",
		max_length=255,
	)
	content: str | None = Field(
		default=None,
		description="body content of the note (markdown supported)",
	)
	labels: list[str] | None = Field(
		default=None,
		description="label strings to tag the note",
	)


class NoteGetTool(Tool[AppContext]):
	"""fetch a specific note by ID or search notes by query."""

	name: str = Field(default="note_get")
	description: str = Field(
		default=(
			"retrieve notes. provide note_id to get a specific note with full content, "
			"or provide a query to search notes by meaning."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: NoteGetInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = NoteGetInput.model_validate(kwargs)

		if inp.note_id:
			# direct fetch by ID
			try:
				note = await note_service.get_note(
					TypeID(inp.note_id),
					__app_context__.session,
					__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			result: dict[str, object] = {
				"status": "success",
				"message": "note retrieved",
				"id": str(note.id),
				"title": note.title,
				"content": note.content,
			}
			if note.labels:
				result["labels"] = [str(label) for label in note.labels]
			return ToolMessage(
				tool_call_id=__agent_context__.tool_call_id,
				tool_output=json.dumps(result),
				metadata={
					"citable_sources": [
						{
							"source_type": "note",
							"source_id": str(note.id),
							"title": note.title,
						},
					],
				},
			)

		if not inp.query:
			return self.error(
				"provide note_id to fetch a note or query to search",
				__agent_context__,
			)

		# search by query
		try:
			page = await note_service.search_notes(
				inp.query,
				__app_context__.session,
				principal=__app_context__.principal,
				limit=inp.limit,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)

		if not page.items:
			out = {
				"status": "success",
				"message": "no notes found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __agent_context__)

		results = [
			{"id": str(item.id), "title": item.title, "subtitle": item.subtitle or ""}
			for item in page.items
		]
		n = len(results)
		msg = f"found {n} {'note' if n == 1 else 'notes'}"
		out = {"status": "success", "message": msg, "count": n, "results": results}
		return self.success(json.dumps(out), __agent_context__)


class NoteWriteTool(Tool[AppContext]):
	"""create a new note or edit an existing one."""

	name: str = Field(default="note_write")
	description: str = Field(
		default=(
			"create or edit a note. omit note_id to create a new note. "
			"provide note_id to update an existing note's title, content, or labels."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: NoteWriteInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		inp = NoteWriteInput.model_validate(kwargs)

		if inp.note_id:
			# update existing note
			try:
				note = await note_service.update_note(
					TypeID(inp.note_id),
					NoteUpdate(
						title=inp.title,
						content=inp.content,
						labels=inp.labels,
					),
					__app_context__.session,
					__app_context__.principal,
				)
			except HTTPException as exc:
				return self.error(str(exc.detail), __agent_context__)
			out = {"status": "success", "message": "note updated", "id": str(note.id)}
			return self.success(json.dumps(out), __agent_context__)

		# create new note
		if not inp.title:
			return self.error(
				"title is required when creating a note", __agent_context__
			)
		try:
			note = await note_service.create_note(
				NoteCreate(
					title=inp.title,
					content=inp.content or "",
					labels=inp.labels or [],
				),
				__app_context__.session,
				__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)
		out = {"status": "success", "message": "note created", "id": str(note.id)}
		return self.success(json.dumps(out), __agent_context__)
