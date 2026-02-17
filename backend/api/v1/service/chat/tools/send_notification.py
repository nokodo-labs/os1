"""send notification tool - lets agents send notifications directly to users."""

from __future__ import annotations

from pydantic import Field

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.v1.service import notifications as notification_service
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.chat.context import AppContext
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


_TOOL_PARAMETERS: JSONObject = {
	"type": "object",
	"properties": {
		"title": {
			"type": "string",
			"description": (
				"short title for the notification. keep it concise and informative."
			),
			"maxLength": 100,
		},
		"body": {
			"type": "string",
			"description": (
				"main content/message of the notification. "
				"provide helpful context for the user."
			),
			"maxLength": 500,
		},
		"user_id": {
			"type": "string",
			"description": (
				"optional: specific user ID to send to. "
				"if omitted, notification goes to all thread participants "
				"(including the thread owner)."
			),
		},
	},
	"required": ["title", "body"],
}


class SendNotificationTool(Tool[AppContext]):
	"""tool for sending notifications to users.

	by default, notifications are sent to all participants in the thread
	(including the owner).
	optionally, a specific user_id can be provided to target one user.
	"""

	name: str = Field(default="send_notification")
	description: str = Field(
		default=(
			"send a notification to thread participants. use this to alert "
			"users about important information, reminders, or updates. "
			"by default notifies all participants (including the owner); "
			"optionally target a specific user."
		)
	)
	parameters: JSONObject = Field(default=_TOOL_PARAMETERS)

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
			target_user_ids = await list_accessible_user_ids(
				ResourceType.THREAD,
				str(ctx.thread_id),
				session,
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
