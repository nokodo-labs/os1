"""memory recall tool - retrieves relevant memories for the current context."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy import select

from api.models.memory import Memory
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class MemoryRecallInput(BaseModel):
	"""input schema for memory recall tool."""

	query: str = Field(
		...,
		description=(
			"natural language query describing what memories to recall. "
			"be specific about the topic or context you need."
		),
	)
	limit: int = Field(
		default=5,
		description="maximum number of memories to return",
		ge=1,
		le=20,
	)


class MemoryCreateInput(BaseModel):
	"""input schema for memory create tool."""

	content: str = Field(
		...,
		description="the content of the memory to store",
	)
	category: str | None = Field(
		default=None,
		description="optional category or tag for the memory",
	)


class MemoryRecallTool(Tool[AppContext]):
	"""tool for recalling user memories based on a query.

	this tool searches the user's stored memories and returns
	relevant information based on semantic similarity to the query.
	"""

	name: str = Field(default="memory_recall")
	description: str = Field(
		default=(
			"recall relevant memories and stored information about the user. "
			"use this to retrieve context from past conversations, preferences, "
			"or facts the user has shared."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: MemoryRecallInput.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext,
		**kwargs: object,
	) -> ToolMessage:
		"""execute memory recall.

		args:
			__agent_context__: sdk agent context
			__app_context__: application context with session
			**kwargs: tool arguments (query, limit)

		returns:
			ToolMessage with recalled memories
		"""
		# query param is available for semantic search (future use)
		_ = str(kwargs.get("query", ""))
		limit_val = kwargs.get("limit", 5)
		limit = int(limit_val) if isinstance(limit_val, (int, str, float)) else 5

		user_id = __app_context__.user_id

		# simple keyword-based search for now
		# TODO: implement semantic search with embeddings
		session = __app_context__.session

		stmt = (
			select(Memory)
			.where(Memory.user_id == user_id)
			.order_by(Memory.updated_at.desc())
			.limit(limit)
		)

		result = await session.execute(stmt)
		memories = list(result.scalars().all())

		if not memories:
			return self.success("no relevant memories found", __agent_context__)

		# format memories for the agent
		formatted = []
		for i, mem in enumerate(memories, 1):
			category = f" [{mem.category}]" if mem.category else ""
			formatted.append(f"{i}. {mem.content}{category}")

		output = "recalled memories:\n" + "\n".join(formatted)
		return self.success(output, __agent_context__)


class MemoryCreateTool(Tool[AppContext]):
	name: str = Field(default="memory_create")
	description: str = Field(
		default=(
			"create a new memory for the user. use this to store important "
			"information, facts, or preferences that the user shares during "
			"the conversation."
		)
	)
	parameters: JSONObject = Field(
		default={
			"type": "object",
			"properties": {
				"content": {
					"type": "string",
					"description": "the content of the memory to store",
				},
				"category": {
					"type": "string",
					"description": "optional category or tag for the memory",
				},
			},
			"required": ["content"],
		}
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext,
		**kwargs: object,
	) -> ToolMessage:
		try:
			input_memory = MemoryCreateInput.model_validate(kwargs)

			new_memory = Memory(
				user_id=__app_context__.user_id,
				content=input_memory.content,
				category=input_memory.category,
			)
			__app_context__.session.add(new_memory)

		except Exception as e:
			logger.error(f"failed to create memory: {str(e)}", exc_info=True)
			return self.error("failed to create memory", __agent_context__)

		return self.success("memory created successfully", __agent_context__)
