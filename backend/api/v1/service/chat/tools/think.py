"""think tool - lets agents reason."""

from __future__ import annotations

import json
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field

from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


class Thought(BaseModel):
	"""individual thought in the agent's reasoning process."""

	text: str = Field(
		...,
		description=(
			"the content of this thought. should be a statement or observation "
			"that contributes to your reasoning process. "
			"escape characters properly to avoid failed JSON parsing."
		),
	)
	summary: str = Field(
		...,
		max_length=50,
		description=(
			"a very brief summary of this thought, ideally 3-5 words. "
			"displayed to users as an overview of your thought process."
		),
	)


class ChainOfThoughts(BaseModel):
	"""structured reasoning output from the agent's thought process."""

	model_config = ConfigDict(extra="forbid")

	thoughts: list[Thought] = Field(
		min_length=1,
		description=(
			"list of individual thoughts that make up your reasoning process."
		),
	)


class ThinkingTool(Tool[AppContext]):
	"""tool for agents to articulate their reasoning process in a structured way."""

	name: str = Field(default="think")
	description: str = Field(
		default=(
			"think, reason, and articulate your thought process. "
			"use this as your internal, private "
			"scratchpad to work through complex problems."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ChainOfThoughts.model_json_schema()
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""process the agent's thoughts and return a timing summary.

		the elapsed time is measured from when the ToolCall object was
		first created (i.e. when the first streaming delta for this
		tool call arrived), capturing the chat model's generation time.
		"""
		start_time = __tool_call_context__.tool_call_start_time
		elapsed_time = monotonic() - start_time
		try:
			chain = ChainOfThoughts.model_validate(kwargs)
		except Exception:
			return self.error(
				json.dumps({"error": "invalid thought structure"}),
				__tool_call_context__,
			)
		return self.success(
			json.dumps(
				{
					"elapsed_seconds": round(elapsed_time, 2),
					"thought_count": len(chain.thoughts),
				}
			),
			__tool_call_context__,
		)
