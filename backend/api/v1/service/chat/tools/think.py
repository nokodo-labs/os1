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
		"""send notification(s) - thread-scoped by default."""
		ctx = __app_context__
		tool_call_id = __agent_context__.tool_call_id

		title = str(kwargs.get("title", ""))
		body = str(kwargs.get("body", ""))
		target_user_id = kwargs.get("user_id")

		if not title or not body:
			return self.error(
				"both title and body are required for notifications",
				__agent_context__,
			)

		session = ctx.session
		agent_id = str(ctx.agent_id) if ctx.agent_id else None
		thread_id = str(ctx.thread_id) if ctx.thread_id else None

		if target_user_id:
			target_user_ids = [str(target_user_id)]
		elif ctx.thread_id is not None:
			target_user_ids = await thread_service.list_thread_recipient_user_ids(
				ctx.thread_id,
				session,
				principal=ctx.principal,
			)
		else:
			return self.error(
				"no recipients: provide user_id or run inside a thread",
				__agent_context__,
			)

		# thread-scoped by default; user_id is opt-in for single-user targeting
		notifications = await notification_service.send_agent_notification(
			session,
			title=title,
			body=body,
			agent_id=agent_id,
			user_ids=target_user_ids,
		)

		# emit tool event for chat UI (with first notification ID for reference)
		first_notification_id = str(notifications[0].id) if notifications else None
		recipient_count = len(notifications)

		tool_event = Event(
			scope=EventScope.THREAD if thread_id else EventScope.USER,
			scope_id=thread_id or str(ctx.user_id),
			type=EventType.TOOL_NOTIFICATION,
			data={
				"tool_call_id": tool_call_id,
				"tool_name": self.name,
				"notification_id": first_notification_id,
				"notification_count": recipient_count,
				"title": title,
				"body": body,
				"target_user_id": str(target_user_id) if target_user_id else None,
				"status": "sent",
			},
			user_id=str(ctx.user_id),
			thread_id=thread_id,
		)
		await ctx.event_emitter(tool_event)

		if recipient_count == 1:
			return self.success(
				f'notification sent: "{title}"',
				__agent_context__,
			)
		return self.success(
			f'notification sent to {recipient_count} participants: "{title}"',
			__agent_context__,
		)
