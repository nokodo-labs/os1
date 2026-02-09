"""think tool - lets agents reason."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.v1.service import notifications as notification_service
from api.v1.service import threads as thread_service
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
		max_length=30,
		description=(
			"a very brief summary of this thought, ideally 3-5 words. used for "
			"display purposes in the UI to give users a quick overview of the agent's "
			"reasoning process. should capture the essence of the thought in a few words."
		),
	)


class ChainOfThoughts(BaseModel):
	"""structured reasoning output from the agent's thought process."""

	thoughts: list[Thought] = Field(
		default_factory=list,
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
			"think, reason, and articulate your thought process in a structured way. "
			"use this as your internal, private scratchpad to work through "
			"complex problems step by step. "
			"use this tool every time you need to stop and reason through something."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: ChainOfThoughts.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext,
		**kwargs: object,
	) -> ToolMessage:
		raise NotImplementedError("WIP")
		"""process the agent's thoughts and emit an event for the UI to consume."""
		chain_of_thoughts = ChainOfThoughts.model_validate(kwargs)
		event = Event(
			type=EventType.agent_thoughts,
			scope=EventScope.thread,
			thread_id=__app_context__.thread_id,
			payload=chain_of_thoughts.model_dump(),
		)
		await notification_service.emit_event(event)

		# return empty content since the value is in the emitted event
		return ToolMessage(content={})
