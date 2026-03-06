"""memories tools - search and create memories."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from pydantic import BaseModel, Field

from api.schemas.memory import MemoryCreate
from api.v1.service import memories as memory_service
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class MemorySearchInput(BaseModel):
	"""input schema for memory_search tool."""

	query: str = Field(
		...,
		description=(
			"natural language query describing what memories to recall. "
			"hybrid BM25 + semantic search is used."
		),
	)
	limit: int = Field(
		default=5,
		description="maximum number of memories to return",
		ge=1,
		le=20,
	)


class MemoryCreateInput(BaseModel):
	"""input schema for memory_create tool."""

	content: str = Field(
		...,
		description="the content of the memory to store",
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
			"recall relevant memories about the user using a semantic query. "
			"use this to retrieve context from past conversations, stated "
			"preferences, or facts the user has shared."
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
			return self.success(
				"memory features are disabled by user preferences",
				__agent_context__,
			)
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
			return self.success("no relevant memories found", __agent_context__)

		lines = []
		for item in page.items:
			subtitle = f" - {item.subtitle}" if item.subtitle else ""
			lines.append(f"- [{item.id}] {item.title}{subtitle}")
		return self.success(
			"recalled memories:\n" + "\n".join(lines), __agent_context__
		)


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
			return self.success(
				"memory features are disabled by user preferences",
				__agent_context__,
			)
		inp = MemoryCreateInput.model_validate(kwargs)
		try:
			memory = await memory_service.create_memory(
				MemoryCreate(
					content=inp.content,
					category=inp.category,
					user_id=__app_context__.user_id,
				),
				__app_context__.session,
				__app_context__.principal,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __agent_context__)

		category = f" [{memory.category}]" if memory.category else ""
		return self.success(
			f"memory stored: [{memory.id}]{category} {memory.content[:80]}",
			__agent_context__,
		)
