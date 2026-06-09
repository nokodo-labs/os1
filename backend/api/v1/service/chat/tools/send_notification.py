"""send notification tool - lets agents send notifications directly to users."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict, Field

from api.database import async_session_local
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.notification import NotificationPayload
from api.v1.service import notifications as notification_service
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.chat.context import AppContext
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class SendNotificationInput(BaseModel):
	"""input schema for send_notification tool."""

	model_config = ConfigDict(extra="forbid")

	title: str = Field(
		...,
		description="short title for the notification. keep it concise.",
		max_length=100,
	)
	body: str | None = Field(
		default=None,
		description="optional message body with helpful context when needed.",
		max_length=500,
	)
	user_id: str | None = Field(
		default=None,
		description=(
			"optional specific user ID. omit to notify all chat participants "
			"including the chat owner. when provided, the target must be a "
			"participant in the current chat unless the caller is an admin."
		),
	)


class SendNotificationTool(Tool[AppContext]):
	"""tool for sending notifications to users.

	by default, notifications are sent to all participants in the thread
	(including the owner).
	optionally, a specific user_id can be provided, but only when that user
	is a participant in the current thread or the caller has admin privileges.
	"""

	name: str = Field(default="send_notification")
	description: str = Field(
		default=(
			"send a notification to chat participants. use this to alert "
			"users about important information, reminders, or updates. "
			"by default notifies all participants (including the owner); "
			"optionally target a specific user."
		)
	)
	parameters: JSONObject = Field(
		default_factory=lambda: SendNotificationInput.model_json_schema()
	)

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""send notification(s) - thread-scoped by default."""
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		ctx = __app_context__

		inp = SendNotificationInput.model_validate(kwargs)

		agent_id = ctx.agent_id
		thread_id = ctx.thread_id

		# use an isolated session to avoid dirtying the shared request session.
		# if any DB operation fails, only this session is affected.
		try:
			async with async_session_local() as tool_session:
				if inp.user_id is not None and ctx.principal.is_admin:
					target_user_ids: list[TypeID] = [TypeID(inp.user_id)]
				else:
					accessible_user_ids: list[TypeID] | None = (
						await list_accessible_user_ids(
							ResourceType.THREAD,
							ctx.thread_id,
							tool_session,
						)
						if ctx.thread_id is not None
						else None
					)
					if inp.user_id is not None:
						if accessible_user_ids is None:
							return self.error(
								"forbidden: targeting a specific user requires a chat context",
								__tool_call_context__,
							)
						target_user_id = TypeID(inp.user_id)
						if target_user_id not in accessible_user_ids:
							return self.error(
								"forbidden: target user is not a participant in this chat",
								__tool_call_context__,
							)
						target_user_ids = [target_user_id]
					elif accessible_user_ids is not None:
						target_user_ids = accessible_user_ids
					else:
						return self.error(
							"no recipients: provide user_id or run inside a chat",
							__tool_call_context__,
						)

				recipient_count = len(target_user_ids)

				# emit tool event first so the emitter auto-assigns its id;
				# each notification's event data then references it (notification -> tool event).
				tool_event = Event(
					scope=EventScope.THREAD if thread_id else EventScope.USER,
					scope_id=thread_id or ctx.user_id,
					type=EventType.TOOL_NOTIFICATION,
					data={
						"tool_call_id": __tool_call_context__.tool_call_id,
						"tool_name": self.name,
						"notification_count": recipient_count,
						"title": inp.title,
						"body": inp.body,
						"target_user_id": inp.user_id,
						"status": "sent",
					},
					user_id=ctx.user_id,
					thread_id=thread_id,
				)
				await ctx.event_emitter(tool_event)

				await notification_service.create_notifications(
					tool_session,
					payload=NotificationPayload(
						title=inp.title,
						body=inp.body,
						data={"tool_event_id": str(tool_event.id)},
					),
					event_type=EventType.NOTIFICATION_AGENT,
					agent_id=agent_id,
					user_ids=target_user_ids,
				)
		except Exception:
			logger.exception("send_notification tool failed")
			return self.error(
				"failed to send notification",
				__tool_call_context__,
			)

		if recipient_count == 1:
			return self.success(
				f'notification sent: "{inp.title}"',
				__tool_call_context__,
			)
		return self.success(
			f'notification sent to {recipient_count} participants: "{inp.title}"',
			__tool_call_context__,
		)
