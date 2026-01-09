"""Regression tests for delete cascades.

Ensures backend delete operations clean up dependent rows:
- soft-deleting a thread does not delete messages
- deleting a message clears its attached events
- deleting a notification clears its attached event (when unshared)
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.message import Message, MessageType
from api.models.notification import Notification
from api.models.thread import Thread
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate
from api.schemas.user import UserCreate
from api.v1.service import notifications as notification_service
from api.v1.service import threads as thread_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID


@pytest.mark.asyncio
async def test_soft_delete_thread_does_not_delete_messages(
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(email="cascade_thread@example.com", password="password123"),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=TypeID(user.id), title="t"),
		db_session,
		principal=principal,
	)

	await thread_service.create_message(
		TypeID(thread.id),
		message_in=MessageCreate(content="hello", type=MessageType.USER),
		session=db_session,
		principal=principal,
	)

	count_before = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_before or 0) == 1

	await thread_service.delete_thread(
		TypeID(thread.id),
		db_session,
		principal=principal,
	)

	remaining = list(
		(
			await db_session.scalars(
				select(Message).where(Message.thread_id == thread.id)
			)
		).all()
	)
	assert len(remaining) == 1

	stmt = (
		select(Thread)
		.where(Thread.id == thread.id)
		.execution_options(include_deleted=True)
	)
	thread_row = (await db_session.execute(stmt)).scalar_one_or_none()
	assert thread_row is not None
	assert thread_row.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_message_also_deletes_attached_events(
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(email="cascade_message@example.com", password="password123"),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=TypeID(user.id), title="t"),
		db_session,
		principal=principal,
	)

	msg = await thread_service.create_message(
		TypeID(thread.id),
		message_in=MessageCreate(content="hello", type=MessageType.USER),
		session=db_session,
		principal=principal,
	)

	event = Event(
		scope=EventScope.MESSAGE,
		scope_id=str(msg.id),
		type="test.event",
		data={},
		user_id=str(user.id),
		thread_id=str(thread.id),
		message_id=str(msg.id),
	)
	db_session.add(event)
	await db_session.commit()
	await db_session.refresh(event)

	await thread_service.delete_user_message_turn(
		TypeID(thread.id),
		TypeID(msg.id),
		db_session,
		principal=principal,
	)

	remaining = await db_session.scalar(
		select(func.count()).select_from(Event).where(Event.id == event.id)
	)
	assert int(remaining or 0) == 0


@pytest.mark.asyncio
async def test_delete_notification_also_deletes_attached_event(
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(email="cascade_notif@example.com", password="password123"),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	event = Event(
		scope=EventScope.USER,
		type="test.notif.event",
		data={},
		user_id=str(user.id),
	)
	db_session.add(event)
	await db_session.flush()

	notification = Notification(user_id=str(user.id), event_id=str(event.id))
	db_session.add(notification)
	await db_session.commit()
	await db_session.refresh(notification)
	await db_session.refresh(event)

	await notification_service.delete_notification(
		str(notification.id),
		db_session,
		principal=principal,
	)

	assert await db_session.get(Notification, notification.id) is None
	assert await db_session.get(Event, event.id) is None
