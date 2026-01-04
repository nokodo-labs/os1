"""send notification tool - lets agents send notifications directly to users."""

from __future__ import annotations

from pydantic import Field
from sqlalchemy import select

from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.v1.service import events as event_service
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
	},
	"required": ["title", "body"],
}


class SendNotificationTool(Tool[AppContext]):
	"""tool for sending notifications directly to the user.

	this allows agents to proactively notify users about important events,
	reminders, or information. the notification will appear in the user's
	dock notification area with the agent's profile icon.
	"""

	name: str = Field(default="send_notification")
	description: str = Field(
		default=(
			"send a notification directly to the user. use this to alert "
			"the user about important information, reminders, or updates. "
			"notifications appear in the user's notification center with "
			"your agent profile icon."
		)
	)
	parameters: JSONObject = Field(default=_TOOL_PARAMETERS)

	async def call(
		self,
		__agent_context__: AgentContext,
		__app_context__: AppContext,
		**kwargs: object,
	) -> ToolMessage:
		"""execute notification send.

		args:
			__agent_context__: sdk agent context
			__app_context__: application context with session
			**kwargs: tool arguments (title, body)

		returns:
			ToolMessage confirming notification was sent
		"""
		title = str(kwargs.get("title", ""))
		body = str(kwargs.get("body", ""))

		if not title or not body:
			return self.error(
				"both title and body are required for notifications",
				__agent_context__,
			)

		session = __app_context__.session
		user_id = str(__app_context__.user_id)
		agent_id = __app_context__.agent_id

		# fetch agent profile image info if available
		agent_profile_url: str | None = None
		agent_name: str | None = None

		if agent_id:
			stmt = select(Agent).where(Agent.id == str(agent_id))
			result = await session.execute(stmt)
			agent = result.scalar_one_or_none()
			if agent:
				agent_name = agent.name
				agent_profile_url = agent.profile_image_url

		# create the event
		event = Event(
			scope=EventScope.USER,
			scope_id=user_id,
			type=EventType.NOTIFICATION_AGENT,
			data={
				"title": title,
				"body": body,
				"agent_id": str(agent_id) if agent_id else None,
				"agent_name": agent_name,
				"icon_url": agent_profile_url,
			},
			user_id=user_id,
		)
		await event_service.publish_event(
			session,
			event=event,
			create_notification=True,
		)

		return self.success(
			f'notification sent to user: "{title}"',
			__agent_context__,
		)
