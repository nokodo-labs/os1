"""memories tools - search and create memories."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.database import async_session_local
from api.schemas.memory import MemoryCreate
from api.tasks import create_background_task
from api.v1.service import memories as memory_service
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONArray, JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class MemorySearchInput(BaseModel):
	"""input schema for memory_search tool."""

	model_config = ConfigDict(extra="forbid")

	query: str = Field(
		...,
		description=("natural language query describing what memories to recall."),
	)
	limit: int = Field(
		default=5,
		description="maximum number of relevant memories to return",
		ge=1,
		le=20,
	)


class MemoryCreateInput(BaseModel):
	"""input schema for memory_create tool."""

	model_config = ConfigDict(extra="forbid")

	content: str = Field(
		...,
		description="the content of the memory to store. "
		"all memories about the user MUST start with `User`.",
		examples=[
			"User's dog Ruby is a golden retriever",
		],
	)
	category: str | None = Field(
		default=None,
		description="optional category or tag for the memory",
	)


class MemoryRecallTool(Tool[AppContext]):
	"""search user memories using hybrid BM25 + semantic search."""

	name: str = Field(default="memory_recall")
	description: str = Field(
		default=(
			"recall memories from your long term memory system "
			"via hybrid vector search."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: MemorySearchInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		ai = __app_context__.principal.user.prefs.ai
		if ai is not None and ai.memories_enabled is False:
			out: JSONObject = {
				"status": "success",
				"message": "memory features are disabled by user preferences",
			}
			return self.success(json.dumps(out), __agent_context__)
		inp = MemorySearchInput.model_validate(kwargs)
		try:
			page = await memory_service.search_memories(
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
				"message": "no memories found",
				"count": 0,
				"results": [],
			}
			return self.success(json.dumps(out), __agent_context__)

		results: JSONArray = [
			{
				"id": item.id,
				"title": item.title,
				**({"category": item.preview} if item.preview else {}),
			}
			for item in page.items
		]
		n = len(results)
		msg = f"recalled {n} {'memory' if n == 1 else 'memories'}"
		out = {"status": "success", "message": msg, "count": n, "results": results}
		return self.success(json.dumps(out), __agent_context__)


class MemoryCreateTool(Tool[AppContext]):
	"""store a new memory for the user."""

	name: str = Field(default="memory_create")
	description: str = Field(
		default=(
			"store a new memory. use this to permanently save important facts, "
			"preferences, or context the user has shared during the conversation."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: MemoryCreateInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		if __app_context__ is None:
			return self.error("app context is required", __agent_context__)
		ai = __app_context__.principal.user.prefs.ai
		if ai is not None and ai.memories_enabled is False:
			disabled_out = {
				"status": "success",
				"message": "memory features are disabled by user preferences",
			}
			return self.success(json.dumps(disabled_out), __agent_context__)
		inp = MemoryCreateInput.model_validate(kwargs)

		# return immediately - persist + vectorize in a background task
		create_background_task(
			_persist_memory(
				inp,
				user_id=__app_context__.user_id,
				principal=__app_context__.principal,
			),
			name=f"memory_create:{__app_context__.user_id}",
		)

		out: JSONObject = {"status": "success", "message": "memory saved"}
		return self.success(json.dumps(out), __agent_context__)


async def _persist_memory(
	inp: MemoryCreateInput,
	user_id: TypeID,
	principal: Principal,
) -> None:
	"""background task: create memory in its own session."""
	try:
		async with async_session_local() as session:
			await memory_service.create_memory(
				MemoryCreate(
					content=inp.content,
					category=inp.category,
					user_id=user_id,
				),
				session,
				principal,
			)
			await session.commit()
	except Exception:
		logger.exception("background memory_create failed")
