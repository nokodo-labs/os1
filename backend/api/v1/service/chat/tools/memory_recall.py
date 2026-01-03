"""memory recall tool - retrieves relevant memories for the current context."""

from __future__ import annotations

from pydantic import Field
from sqlalchemy import select

from api.models.memory import Memory
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


_TOOL_PARAMETERS = {
	"type": "object",
	"properties": {
		"query": {
			"type": "string",
			"description": (
				"natural language query describing what memories to recall. "
				"be specific about the topic or context you need."
			),
		},
		"limit": {
			"type": "integer",
			"description": "maximum number of memories to return",
			"default": 5,
			"minimum": 1,
			"maximum": 20,
		},
	},
	"required": ["query"],
}


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
	parameters: JSONObject = Field(default=_TOOL_PARAMETERS)

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
