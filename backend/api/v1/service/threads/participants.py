"""service helpers for threads and messages."""

from __future__ import annotations

import logging

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.permissions import ResourceType
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	list_accessible_user_ids,
	require_thread_access,
	thread_access_predicate,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def handle_typing_event(
	session: AsyncSession,
	user_id: TypeID,
	thread_id: TypeID,
	typing: bool,
) -> None:
	"""broadcast a typing indicator to all users with access to a thread.

	ephemeral: no event persistence, just fan-out over WS.
	the sender must be among the accessible users; if not, the event is
	silently dropped (prevents spam for threads the user has no access to).
	"""
	recipient_ids = await list_accessible_user_ids(
		ResourceType.THREAD,
		thread_id,
		session,
	)

	if not recipient_ids or user_id not in recipient_ids:
		return

	msg_type = "typing.start" if typing else "typing.stop"
	payload = {
		"type": msg_type,
		"data": {
			"thread_id": thread_id,
			"user_id": user_id,
		},
	}

	await event_service.event_connections.send_to_users(
		recipient_ids,
		payload,
		exclude_user_id=user_id,
	)


# --- thread participant helpers ---


async def ensure_participant(
	thread_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
) -> ThreadParticipant:
	"""get or create a participant row for a user in a thread."""
	stmt = select(ThreadParticipant).where(
		ThreadParticipant.thread_id == thread_id,
		ThreadParticipant.user_id == user_id,
		ThreadParticipant.left_at.is_(None),
	)
	result = await session.execute(stmt)
	existing = result.scalars().first()
	if existing:
		return existing

	participant = ThreadParticipant(
		thread_id=thread_id,
		user_id=user_id,
	)
	session.add(participant)
	await session.flush()
	return participant


async def mark_thread_read(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ThreadParticipant:
	"""mark all messages in a thread as read for the current user.

	sets last_read_message_id to the latest message in the thread.
	"""
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)

	participant = await ensure_participant(thread_id, principal.user.id, session)

	# find the latest message in the thread
	latest_stmt = (
		select(Message.id)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at.desc())
		.limit(1)
	)
	result = await session.execute(latest_stmt)
	latest_id = result.scalar_one_or_none()

	if latest_id:
		participant.last_read_message_id = latest_id

	await session.flush()

	# notify all thread participants (read receipts)
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_READ,
			data={
				"thread_id": str(thread_id),
				"user_id": principal.user_id,
				"last_read_message_id": str(latest_id) if latest_id else None,
			},
			user_id=principal.user_id,
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)

	return participant


async def get_unread_counts(
	session: AsyncSession,
	principal: Principal,
	thread_ids: list[TypeID] | None = None,
) -> dict[TypeID, int]:
	"""return unread message counts per thread for the current user.

	for threads with no participant row, all messages are considered unread.
	for threads with a participant row but no last_read_message_id, all
	messages are also considered unread.
	"""
	user_id = principal.user.id

	accessible_q = (
		select(Thread.id)
		.where(
			thread_access_predicate(
				principal,
				required_level=AccessLevel.READER,
			)
		)
		.where(Thread.is_temporary.is_(False))
	)
	if thread_ids:
		accessible_q = accessible_q.where(Thread.id.in_(thread_ids))
	accessible_subq = accessible_q.scalar_subquery()

	# left join participants to get last_read_message's created_at.
	# count messages after that timestamp (or all if no read state).
	last_read_ts = (
		select(Message.created_at)
		.where(Message.id == ThreadParticipant.last_read_message_id)
		.correlate(ThreadParticipant)
		.scalar_subquery()
	)

	part_alias = (
		select(
			ThreadParticipant.thread_id,
			last_read_ts.label("read_at"),
		)
		.where(
			ThreadParticipant.user_id == user_id,
			ThreadParticipant.left_at.is_(None),
		)
		.subquery("part")
	)

	stmt = (
		select(
			Message.thread_id,
			func.count(Message.id).label("cnt"),
		)
		.where(Message.thread_id.in_(accessible_subq))
		.outerjoin(part_alias, Message.thread_id == part_alias.c.thread_id)
		.where(
			or_(
				Message.sender_user_id.is_(None),
				Message.sender_user_id != str(principal.user.id),
			),
			or_(
				part_alias.c.read_at.is_(None),
				Message.created_at > part_alias.c.read_at,
			),
		)
		.group_by(Message.thread_id)
	)

	result = await session.execute(stmt)
	return {TypeID(row.thread_id): row.cnt for row in result if row.cnt > 0}
