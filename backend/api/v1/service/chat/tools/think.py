"""think tool - lets agents reason."""

from __future__ import annotations

import json
from time import time

from pydantic import BaseModel, ConfigDict, Field

from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


class Thought(BaseModel):
	"""individual thought in the agent's reasoning process."""

	text: str = Field(
		...,
		description=(
			"the content of this thought. should be a concise statement or observation "
			"that contributes to the agent's overall reasoning process."
		),
	)
	summary: str = Field(
		...,
		max_length=50,
		description=(
			"a very brief summary of this thought, ideally 3-5 words. "
			"used for display purposes in the UI to give users a quick "
			"overview of the agent's reasoning process. should capture "
			"the essence of the thought in a few words."
		),
	)


class ChainOfThoughts(BaseModel):
	"""structured reasoning output from the agent's thought process."""

	model_config = ConfigDict(extra="forbid")

	thoughts: list[Thought] = Field(
		min_length=1,
		description=(
			"list of individual thoughts that make up the agent's reasoning process."
		),
	)


class ThinkingTool(Tool[AppContext]):
	"""tool for agents to articulate their reasoning process in a structured way."""

	name: str = Field(default="think")
	description: str = Field(
		default=(
			"think, reason, and articulate your thought process in a "
			"structured way. use this as your internal, private "
			"scratchpad to work through complex problems. "
			"use this tool every time you need to stop and reason "
			"through something.\n\n"
			"NEVER use this tool before saying anything to the user. "
			"always prioritize feedback, by saying something like "
			"'let me think about that' before using this tool for the "
			"first time in your turn."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ChainOfThoughts.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""process the agent's thoughts and return a timing summary.

		the elapsed time is measured from when the ToolCall object was
		first created (i.e. when the first streaming delta for this
		tool call arrived), capturing the chat model's generation time.
		"""
		elapsed_time = time() - __agent_context__.tool_call_start_time
		try:
			chain = ChainOfThoughts.model_validate(kwargs)
		except Exception:
			return self.error(
				json.dumps({"error": "invalid thought structure"}),
				__agent_context__,
			)
		return self.success(
			json.dumps(
				{
					"elapsed_seconds": round(elapsed_time, 2),
					"thought_count": len(chain.thoughts),
				}
			),
			__agent_context__,
		)
