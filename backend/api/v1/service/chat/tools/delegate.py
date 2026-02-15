"""think tool - lets agents reason."""

from __future__ import annotations

import json
from time import time
from typing import Literal

from pydantic import BaseModel, Field

from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


class DelegateTarget(BaseModel):
	"""the target to delegate a task to."""

	type: Literal["agent"] = Field(
		default="agent",
		description=(
			"the type of entity to delegate the task to. currently only delegating to "
			"agents is supported."
		),
	)
	id: Literal["self"] = Field(
		default="self",
		description=(
			"the specific entity to delegate the task to. currently, the only "
			"supported value is 'self', which means to delegate the task to a new "
			"sub-agent instance of the current agent."
		),
	)


class DelegateRequest(BaseModel):
	"""request body for delegating a task to a sub-agent."""

	target: DelegateTarget = Field(
		default_factory=DelegateTarget,
		description="the target to delegate the task to. omit to delegate to a "
		"separate instance of yourself.",
	)
	message: str = Field(
		...,
		description=(
			"a description of the task to delegate. should be "
			"specific and actionable, describing a clear objective to accomplish. "
			"this message will be the first in the target's sub-thread."
		),
	)
	run_in_background: bool = Field(
		default=True,
		description=(
			"whether the delegated task should be run in the background.\n\nif true, "
			"this tool will immediately output with the task ID. you can then use "
			"this ID to check the status of the task or retrieve its results at any "
			"point. this allows you to complete other tasks in parallel.\nmake "
			"sure the delegated tasks will never conflict with yours or each other, "
			"if run in parallel. otherwise, race conditions and failures will "
			"occur.\n\n"
			"if false, this tool will await the completion of the delegated task "
			"before returning the result.\nuse this when your main concern is "
			"CONTEXT USAGE - as this will effectively compress all sub-tasks "
			"needed to accomplish a task, into a single efficient tool call."
		),
	)


class DelegateTool(Tool[AppContext]):
	"""tool for agents to articulate their reasoning process in a structured way."""

	name: str = Field(default="delegate")
	description: str = Field(
		default=(
			"delegate tasks to sub-agents in a structured way. use this tool to "
			"assign specific tasks to other agents or sub-agents, allowing for "
			"parallel processing and efficient task management.\n\n"
			"NEVER use this tool before saying anything to the user. "
			"always prioritize feedback, by saying something like "
			"'let me think about that' before using this tool for the "
			"first time in your turn."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: DelegateRequest.model_json_schema()
	)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext,
		**kwargs: object,
	) -> ToolMessage:
		"""create a new sub-agent and delegate a task to it."""
		request = DelegateRequest.model_validate(kwargs)
		start_time = time()
		# TODO implement delegation logic to create sub-agent and delegate task
		# for now, just return a placeholder response
		response = {
			"task_id": "placeholder_task_id",
			"status": "pending",
			"result": None,
		}
		return ToolMessage(
			tool_output=json.dumps(response),
			tool_call_id=__agent_context__.tool_call_id,
			metadata={
				"tool_response": True,
				"timestamp": time(),
			},
		)
