"""message-event filter - folds durable thread activity events into context"""

import logging
from collections.abc import Mapping

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.event_types import THREAD_INLINE_ACTIVITY_EVENTS, EventType
from api.models.group import Group
from api.models.user import User
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.filters.base import Filter
from api.v1.service.chat.message_metadata import MESSAGE_ID_KEY
from nokodo_ai.agents import AgentIterationState
from nokodo_ai.context import AgentContext
from nokodo_ai.messages import Message
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


class MessageEventFilter(Filter):
	"""interleave thread activity events as system messages by their anchor."""

	name: str = Field(default="message_event")
	description: str = Field(
		default="folds durable thread activity events (membership changes) into"
		" the agent context as system messages anchored to their message id"
	)

	async def run(
		self,
		state: AgentIterationState[AppContext],
		agent_context: AgentContext,
		app_context: AppContext | None,
	) -> AgentIterationState[AppContext]:
		"""insert activity events as system messages after their anchor."""
		_ = agent_context
		if app_context is None or app_context.thread_id is None:
			return state

		# an event renders inline iff it carries a message_id anchor; user-state
		# updates carry none and are skipped here.
		stmt = (
			select(Event)
			.where(
				Event.thread_id == str(app_context.thread_id),
				Event.type.in_(THREAD_INLINE_ACTIVITY_EVENTS),
				Event.message_id.is_not(None),
			)
			.order_by(Event.created_at)
		)
		events = list((await app_context.session.execute(stmt)).scalars().all())
		if not events:
			return state

		names = await self._resolve_names(app_context.session, events)

		# group rendered system messages by their anchor message id, preserving
		# event order.
		by_anchor: dict[str, list[Message]] = {}
		for event in events:
			texts = self._render(event, names)
			if not texts or event.message_id is None:
				continue
			by_anchor.setdefault(str(event.message_id), []).extend(
				SDKSystemMessage.from_text(text) for text in texts
			)

		if not by_anchor:
			return state

		thread = state.thread
		rebuilt: list[Message] = []
		for msg in thread.messages:
			rebuilt.append(msg)
			message_id = (msg.metadata or {}).get(MESSAGE_ID_KEY)
			if isinstance(message_id, str) and message_id in by_anchor:
				rebuilt.extend(by_anchor[message_id])
		thread.messages = rebuilt
		return state

	@staticmethod
	async def _resolve_names(
		session: AsyncSession, events: list[Event]
	) -> dict[str, str]:
		"""batch-resolve user + group display names referenced by acl events."""
		user_ids: set[str] = set()
		group_ids: set[str] = set()
		for event in events:
			data: JSONObject = event.data or {}
			actor = data.get("actor_user_id")
			if isinstance(actor, str):
				user_ids.add(actor)
			changes = data.get("changes")
			if not isinstance(changes, list):
				continue
			for change in changes:
				if not isinstance(change, dict):
					continue
				for snapshot in (change.get("before"), change.get("after")):
					if not isinstance(snapshot, dict):
						continue
					user_id = snapshot.get("subject_user_id")
					group_id = snapshot.get("subject_group_id")
					if isinstance(user_id, str):
						user_ids.add(user_id)
					if isinstance(group_id, str):
						group_ids.add(group_id)
		names: dict[str, str] = {}
		if user_ids:
			rows = (
				await session.execute(
					select(User.id, User.display_name, User.username).where(
						User.id.in_(list(user_ids))
					)
				)
			).all()
			for uid, display_name, username in rows:
				names[str(uid)] = display_name or username
		if group_ids:
			rows = (
				await session.execute(
					select(Group.id, Group.name).where(Group.id.in_(list(group_ids)))
				)
			).all()
			for gid, name in rows:
				names[str(gid)] = name
		return names

	@staticmethod
	def _render(event: Event, names: dict[str, str]) -> list[str]:
		"""build system-message text for each activity transition."""
		data: JSONObject = event.data or {}
		actor_id = data.get("actor_user_id")
		actor = (
			names.get(actor_id, "someone") if isinstance(actor_id, str) else "someone"
		)

		# agent presence rides the participant types (kind == "agent"); only the
		# anchored add/remove instances reach here, so they always render.
		if data.get("kind") == "agent":
			agent = _name(data.get("agent_name"), "an assistant")
			actor = _name(data.get("actor_name"), actor)
			if event.type == EventType.THREAD_PARTICIPANT_ADDED:
				return [f"{actor} added the assistant {agent} to the conversation."]
			if event.type == EventType.THREAD_PARTICIPANT_REMOVED:
				return [f"{actor} removed the assistant {agent} from the conversation."]
			return []
		if event.type != EventType.ACCESS_UPDATED:
			return []
		changes = data.get("changes")
		if not isinstance(changes, list):
			return []
		return [
			text
			for change in changes
			if isinstance(change, dict)
			if (
				text := MessageEventFilter._render_access_change(
					change,
					actor,
					actor_id if isinstance(actor_id, str) else None,
					names,
				)
			)
		]

	@staticmethod
	def _render_access_change(
		change: Mapping[str, object],
		actor: str,
		actor_id: str | None,
		names: dict[str, str],
	) -> str | None:
		"""render one canonical ACL before/after transition."""
		before = change.get("before")
		after = change.get("after")
		before_rule = before if isinstance(before, dict) else None
		after_rule = after if isinstance(after, dict) else None
		rule = after_rule or before_rule
		if rule is None:
			return None
		user_id = rule.get("subject_user_id")
		group_id = rule.get("subject_group_id")
		subject_id = group_id if isinstance(group_id, str) else user_id
		subject = names.get(subject_id, "someone") if subject_id else "everyone"
		is_group = isinstance(group_id, str)
		is_self = actor_id is not None and actor_id == subject_id
		if before_rule is None:
			level = after_rule.get("level") if after_rule else None
			if is_group:
				return f"{actor} shared this conversation with the group {subject}."
			if level == "reader":
				return f"{actor} invited {subject} to the conversation."
			return f"{actor} added {subject} to the conversation."
		if after_rule is None:
			if is_group:
				return f"{actor} removed the group {subject} from the conversation."
			if is_self:
				return f"{subject} left the conversation."
			return f"{actor} removed {subject} from the conversation."
		level = after_rule.get("level")
		if is_self and level != "reader":
			return f"{subject} joined the conversation."
		target = f"the group {subject}" if is_group else subject
		return f"{actor} changed {target}'s access to {level}."


def _name(value: object, fallback: str) -> str:
	"""coerce a denormalized name field to a display string."""
	return value if isinstance(value, str) and value else fallback
