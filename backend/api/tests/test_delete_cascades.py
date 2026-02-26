"""Regression tests for delete cascades.

Ensures backend delete operations clean up dependent rows:
- soft-deleting a thread does not delete messages
- deleting a message clears its attached events
- deleting a notification clears its attached event (when unshared)
- deleting a user message deletes entire descendant subtree
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
		UserCreate(
			email="cascade_thread@example.com",
			password="password123",
			is_superuser=True,
		),
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
		UserCreate(
			email="cascade_message@example.com",
			password="password123",
			is_superuser=True,
		),
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
		UserCreate(
			email="cascade_notif@example.com",
			password="password123",
			is_superuser=True,
		),
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


@pytest.mark.asyncio
async def test_delete_user_message_deletes_entire_subtree(
	db_session: AsyncSession,
) -> None:
	"""deleting a user message must remove all descendants recursively.

	tree structure:
		root_user
		├── assistant_1 (run 1)
		│   └── followup_user
		│       └── followup_assistant
		└── assistant_2 (run 2, regeneration)

	deleting root_user should remove all 5 messages (4 children + itself).
	"""
	user = await user_service.create_user(
		UserCreate(
			email="subtree_delete@example.com",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=TypeID(user.id), title="t"),
		db_session,
		principal=principal,
	)
	tid = TypeID(thread.id)

	root_user = await thread_service.create_message(
		tid,
		MessageCreate(content="hello", type=MessageType.USER),
		session=db_session,
		principal=principal,
	)

	assistant_1 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="reply 1",
			type=MessageType.ASSISTANT,
			parent_id=root_user.id,
		),
		session=db_session,
		principal=principal,
	)

	followup_user = await thread_service.create_message(
		tid,
		MessageCreate(
			content="follow up",
			type=MessageType.USER,
			parent_id=assistant_1.id,
		),
		session=db_session,
		principal=principal,
	)

	followup_assistant = await thread_service.create_message(
		tid,
		MessageCreate(
			content="follow up reply",
			type=MessageType.ASSISTANT,
			parent_id=followup_user.id,
		),
		session=db_session,
		principal=principal,
	)

	# alternate regeneration branch from root_user
	assistant_2 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="reply 2",
			type=MessageType.ASSISTANT,
			parent_id=root_user.id,
		),
		session=db_session,
		principal=principal,
	)

	count_before = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_before or 0) == 5

	await thread_service.delete_user_message_turn(
		tid,
		TypeID(root_user.id),
		db_session,
		principal=principal,
	)

	count_after = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_after or 0) == 0

	# thread leaf should be cleared since all messages are gone
	await db_session.refresh(thread)
	assert thread.current_message_id is None


@pytest.mark.asyncio
async def test_delete_user_message_preserves_siblings(
	db_session: AsyncSession,
) -> None:
	"""deleting one version of a user message must not affect its sibling edits.

	tree structure:
		precursor_user (root)
		└── precursor_assistant
		    ├── user_v1 (original)  ← delete this
		    │   └── assistant_1
		    └── user_v2 (edit, same parent)
		        └── assistant_2

	deleting user_v1 should remove user_v1 + assistant_1 but
	keep precursor_*, user_v2, and assistant_2.
	"""
	user = await user_service.create_user(
		UserCreate(
			email="sibling_delete@example.com",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=TypeID(user.id), title="t"),
		db_session,
		principal=principal,
	)
	tid = TypeID(thread.id)

	# precursor pair (root of the tree)
	precursor_user = await thread_service.create_message(
		tid,
		MessageCreate(content="precursor", type=MessageType.USER),
		session=db_session,
		principal=principal,
	)

	precursor_assistant = await thread_service.create_message(
		tid,
		MessageCreate(
			content="precursor reply",
			type=MessageType.ASSISTANT,
			parent_id=precursor_user.id,
		),
		session=db_session,
		principal=principal,
	)

	# first version of the follow-up user message
	user_v1 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="version 1",
			type=MessageType.USER,
			parent_id=precursor_assistant.id,
		),
		session=db_session,
		principal=principal,
	)

	assistant_1 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="reply to v1",
			type=MessageType.ASSISTANT,
			parent_id=user_v1.id,
		),
		session=db_session,
		principal=principal,
	)

	# sibling user message (same parent as user_v1 = edit/version)
	user_v2 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="version 2",
			type=MessageType.USER,
			parent_id=precursor_assistant.id,
		),
		session=db_session,
		principal=principal,
	)

	assistant_2 = await thread_service.create_message(
		tid,
		MessageCreate(
			content="reply to v2",
			type=MessageType.ASSISTANT,
			parent_id=user_v2.id,
		),
		session=db_session,
		principal=principal,
	)

	count_before = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_before or 0) == 6

	await thread_service.delete_user_message_turn(
		tid,
		TypeID(user_v1.id),
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
	remaining_ids = {m.id for m in remaining}

	# siblings and their descendants must survive
	assert precursor_user.id in remaining_ids
	assert precursor_assistant.id in remaining_ids
	assert user_v2.id in remaining_ids
	assert assistant_2.id in remaining_ids

	# deleted subtree must be gone
	assert user_v1.id not in remaining_ids
	assert assistant_1.id not in remaining_ids

	# thread leaf should point to the deepest remaining leaf
	await db_session.refresh(thread)
	assert thread.current_message_id == assistant_2.id
