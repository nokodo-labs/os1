"""Regression tests for delete cascades.

Ensures backend delete operations clean up dependent rows:
- soft-deleting a thread does not delete messages
- deleting a message clears its attached events
- deleting a notification clears its attached event (when unshared)
- deleting a user message deletes entire descendant subtree
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.event import Event, EventScope
from api.models.message import Message, MessageType, UserMessage
from api.models.note import Note
from api.models.notification import Notification
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ActionPermission, ResourceType
from api.schemas.message import MessageSplice, ResourceAttachment, TextContent
from api.schemas.thread import ThreadCreate
from api.schemas.user import UserCreate
from api.v1.service import notifications as notification_service
from api.v1.service import threads as thread_service
from api.v1.service import users as user_service
from api.v1.service.authentication import Principal
from api.v1.service.resource_origins import (
	assign_resource_origins,
	load_originated_resources,
)
from api.v1.service.resource_origins.deletion import (
	delete_originated_resources,
	delete_thread_with_originated_resources,
	delete_user_message_turn_with_originated_resources,
)
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.utils.typeid import TypeID


@pytest.mark.asyncio
async def test_soft_delete_thread_does_not_delete_messages(
	db_session: AsyncSession,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="cascade_thread@example.com",
			password="password123",
			username="cascade_thread",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="t"),
		db_session,
		principal=principal,
	)

	await thread_service.create_message(
		thread.id,
		draft=MessageDraft(content=[TextContent(text="hello")], type=MessageType.USER),
		session=db_session,
		principal=principal,
	)

	count_before = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_before or 0) == 1

	with patch(
		"api.v1.service.threads.core.remove_vectorized_resource",
		new=AsyncMock(),
	):
		await thread_service.delete_thread(
			thread.id,
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
			username="cascade_message",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="t"),
		db_session,
		principal=principal,
	)

	msg = (
		await thread_service.create_message(
			thread.id,
			draft=MessageDraft(
				content=[TextContent(text="hello")], type=MessageType.USER
			),
			session=db_session,
			principal=principal,
		)
	).message

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
		thread.id,
		msg.id,
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
			username="cascade_notif",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	event = Event(
		scope=EventScope.USER,
		type="test.notif.event",
		data={},
		user_id=str(user.id),
	)
	db_session.add(event)
	await db_session.flush()

	notification = Notification(
		user_id=str(user.id),
		event_id=str(event.id),
		title="cascade notification",
	)
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
			username="subtree_delete",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="t"),
		db_session,
		principal=principal,
	)
	tid = thread.id

	root_user = (
		await thread_service.create_message(
			tid,
			MessageDraft(content=[TextContent(text="hello")], type=MessageType.USER),
			session=db_session,
			principal=principal,
		)
	).message

	assistant_1 = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="reply 1")],
				type=MessageType.ASSISTANT,
				splice=MessageSplice(parent_id=root_user.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	followup_user = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="follow up")],
				type=MessageType.USER,
				splice=MessageSplice(parent_id=assistant_1.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	_ = await thread_service.create_message(
		tid,
		MessageDraft(
			content=[TextContent(text="follow up reply")],
			type=MessageType.ASSISTANT,
			splice=MessageSplice(parent_id=followup_user.id),
		),
		session=db_session,
		principal=principal,
	)

	# alternate regeneration branch from root_user
	_ = await thread_service.create_message(
		tid,
		MessageDraft(
			content=[TextContent(text="reply 2")],
			type=MessageType.ASSISTANT,
			splice=MessageSplice(parent_id=root_user.id),
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
		root_user.id,
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
			username="sibling_delete",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="t"),
		db_session,
		principal=principal,
	)
	tid = thread.id

	# precursor pair (root of the tree)
	precursor_user = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="precursor")], type=MessageType.USER
			),
			session=db_session,
			principal=principal,
		)
	).message

	precursor_assistant = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="precursor reply")],
				type=MessageType.ASSISTANT,
				splice=MessageSplice(parent_id=precursor_user.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	# first version of the follow-up user message
	user_v1 = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="version 1")],
				type=MessageType.USER,
				splice=MessageSplice(parent_id=precursor_assistant.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	assistant_1 = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="reply to v1")],
				type=MessageType.ASSISTANT,
				splice=MessageSplice(parent_id=user_v1.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	# sibling user message (same parent as user_v1 = edit/version)
	user_v2 = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="version 2")],
				type=MessageType.USER,
				splice=MessageSplice(parent_id=precursor_assistant.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	assistant_2 = (
		await thread_service.create_message(
			tid,
			MessageDraft(
				content=[TextContent(text="reply to v2")],
				type=MessageType.ASSISTANT,
				splice=MessageSplice(parent_id=user_v2.id),
			),
			session=db_session,
			principal=principal,
		)
	).message

	count_before = await db_session.scalar(
		select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
	)
	assert int(count_before or 0) == 6

	await thread_service.delete_user_message_turn(
		tid,
		user_v1.id,
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


@pytest.mark.asyncio
async def test_delete_user_cascades_owned_rows(db_session: AsyncSession) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="delete-owner-admin@example.com",
			password="password123",
			username="delete_owner_admin",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=admin, group_ids=(), permissions=frozenset())
	target = await user_service.create_user(
		UserCreate(
			email="delete-owner-target@example.com",
			password="password123",
			username="delete_owner_target",
		),
		db_session,
		principal=principal,
	)
	note = Note(
		user_id=target.id,
		title="delete me",
		content="owned by deleted user",
	)
	db_session.add(note)
	await db_session.commit()
	await db_session.refresh(note)

	await user_service.delete_user(target.id, db_session, principal=principal)

	assert await db_session.get(User, target.id) is None
	assert await db_session.get(Note, note.id) is None


@pytest.mark.asyncio
async def test_originating_someone_elses_resource_is_rejected(
	db_session: AsyncSession,
) -> None:
	"""claiming origin requires owning the resource, not merely reading it.

	an unowned, unclaimed resource must not become deletable-by-cascade just
	because another user names it in their own message.
	"""
	admin = await user_service.create_user(
		UserCreate(
			email="origin-admin@example.com",
			password="password123",
			username="origin_admin",
			is_superuser=True,
		),
		db_session,
	)
	admin_principal = Principal.for_user(
		user=admin, group_ids=(), permissions=frozenset()
	)
	owner = await user_service.create_user(
		UserCreate(
			email="origin-owner@example.com",
			password="password123",
			username="origin_owner",
		),
		db_session,
		principal=admin_principal,
	)
	attacker = await user_service.create_user(
		UserCreate(
			email="origin-attacker@example.com",
			password="password123",
			username="origin_attacker",
		),
		db_session,
		principal=admin_principal,
	)
	attacker_principal = Principal.for_user(
		user=attacker,
		group_ids=(),
		permissions=frozenset({ActionPermission.THREADS_CREATE}),
	)

	note = Note(user_id=owner.id, title="not yours", content="owned elsewhere")
	db_session.add(note)
	await db_session.flush()
	db_session.add(
		AccessRule(
			note_id=note.id,
			subject_user_id=attacker.id,
			level=AccessLevel.EDITOR,
		)
	)
	await db_session.commit()

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=attacker.id, title="t"),
		db_session,
		principal=attacker_principal,
	)
	message = (
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="claiming this")],
				type=MessageType.USER,
			),
			session=db_session,
			principal=attacker_principal,
			originated_resources=[
				ResourceAttachment(type=ResourceType.NOTE, id=note.id)
			],
		)
	).message

	await db_session.refresh(note)
	assert note.origin_message_id is None
	await delete_user_message_turn_with_originated_resources(
		thread.id,
		message.id,
		db_session,
		principal=attacker_principal,
	)
	assert await db_session.get(Note, note.id) is not None


@pytest.mark.asyncio
async def test_owned_resource_can_be_claimed_as_origin(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-positive@example.com",
		username="origin_positive",
		hashed_password="pw",
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="positive origin")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	note = Note(user_id=owner.id, title="claim me", content="origin")
	db_session.add_all([message, note])
	await db_session.flush()

	claimed = await assign_resource_origins(
		message.id,
		[ResourceAttachment(type=ResourceType.NOTE, id=note.id)],
		db_session,
		Principal.for_user(user=owner, group_ids=(), permissions=frozenset()),
	)

	assert claimed == [(ResourceType.NOTE, note.id)]
	await db_session.refresh(note)
	assert note.origin_message_id == message.id


@pytest.mark.asyncio
async def test_already_originated_resource_cannot_be_reclaimed(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-reclaim@example.com",
		username="origin_reclaim",
		hashed_password="pw",
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="immutable origin")
	db_session.add(thread)
	await db_session.flush()
	first_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	second_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	note = Note(user_id=owner.id, title="already claimed", content="origin")
	db_session.add_all([first_message, second_message, note])
	await db_session.flush()
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	attachment = ResourceAttachment(type=ResourceType.NOTE, id=note.id)
	assert await assign_resource_origins(
		first_message.id,
		[attachment],
		db_session,
		principal,
	) == [(ResourceType.NOTE, note.id)]

	assert (
		await assign_resource_origins(
			second_message.id,
			[attachment],
			db_session,
			principal,
		)
		== []
	)
	await db_session.refresh(note)
	assert note.origin_message_id == first_message.id


@pytest.mark.asyncio
async def test_editor_cannot_claim_unoriginated_resource(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-editor-owner@example.com",
		username="origin_editor_owner",
		hashed_password="pw",
	)
	editor = User(
		email="origin-editor@example.com",
		username="origin_editor",
		hashed_password="pw",
	)
	db_session.add_all([owner, editor])
	await db_session.flush()
	thread = Thread(owner_id=editor.id, title="editor origin attempt")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=editor.id)
	note = Note(user_id=owner.id, title="not editor claimable", content="origin")
	db_session.add_all([message, note])
	await db_session.flush()
	db_session.add(
		AccessRule(
			note_id=note.id,
			subject_user_id=editor.id,
			level=AccessLevel.EDITOR,
		)
	)
	await db_session.flush()

	assert (
		await assign_resource_origins(
			message.id,
			[ResourceAttachment(type=ResourceType.NOTE, id=note.id)],
			db_session,
			Principal.for_user(user=editor, group_ids=(), permissions=frozenset()),
		)
		== []
	)
	await db_session.refresh(note)
	assert note.origin_message_id is None


@pytest.mark.asyncio
async def test_load_originated_resources_returns_exact_message_set(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-load@example.com",
		username="origin_load",
		hashed_password="pw",
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="load origins")
	db_session.add(thread)
	await db_session.flush()
	first_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	second_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	third_message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add_all([first_message, second_message, third_message])
	await db_session.flush()
	first_note = Note(
		user_id=owner.id,
		title="first origin",
		content="origin",
		origin_message_id=first_message.id,
	)
	second_note = Note(
		user_id=owner.id,
		title="second origin",
		content="origin",
		origin_message_id=second_message.id,
	)
	other_note = Note(
		user_id=owner.id,
		title="other origin",
		content="origin",
		origin_message_id=third_message.id,
	)
	db_session.add_all([first_note, second_note, other_note])
	await db_session.flush()

	loaded = await load_originated_resources(
		[first_message.id, second_message.id],
		db_session,
	)

	assert set(loaded) == {
		(ResourceType.NOTE, first_note.id),
		(ResourceType.NOTE, second_note.id),
	}


@pytest.mark.asyncio
async def test_message_origin_cascade_is_opt_in_and_ignores_attachments(
	db_session: AsyncSession,
) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="origin-message-cascade@example.com",
			password="password123",
			username="origin_message_cascade",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=admin, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=admin.id, title="message origin cascade"),
		db_session,
		principal=principal,
	)
	originated_note = Note(user_id=admin.id, title="originated", content="delete")
	attached_note = Note(user_id=admin.id, title="attached", content="keep")
	db_session.add_all([originated_note, attached_note])
	await db_session.flush()
	first_message = (
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="default false")],
				type=MessageType.USER,
			),
			db_session,
			principal=principal,
			originated_resources=[
				ResourceAttachment(type=ResourceType.NOTE, id=originated_note.id)
			],
		)
	).message
	await thread_service.delete_user_message_turn(
		thread.id,
		first_message.id,
		db_session,
		principal=principal,
	)
	assert await db_session.get(Note, originated_note.id) is not None

	second_message = (
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="cascade true")],
				type=MessageType.USER,
				attachments=[
					ResourceAttachment(type=ResourceType.NOTE, id=attached_note.id)
				],
			),
			db_session,
			principal=principal,
			originated_resources=[
				ResourceAttachment(type=ResourceType.NOTE, id=originated_note.id)
			],
		)
	).message
	await delete_user_message_turn_with_originated_resources(
		thread.id,
		second_message.id,
		db_session,
		principal=principal,
	)
	assert await db_session.get(Note, attached_note.id) is not None
	stmt = (
		select(Note)
		.where(Note.id == originated_note.id)
		.execution_options(include_deleted=True)
	)
	deleted_note = (await db_session.execute(stmt)).scalar_one()
	assert deleted_note.deleted_at is not None


@pytest.mark.asyncio
async def test_thread_origin_cascade_is_opt_in(db_session: AsyncSession) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="origin-thread-cascade@example.com",
			password="password123",
			username="origin_thread_cascade",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal.for_user(user=admin, group_ids=(), permissions=frozenset())
	first_thread = await thread_service.create_thread(
		ThreadCreate(owner_id=admin.id, title="thread cascade default"),
		db_session,
		principal=principal,
	)
	first_note = Note(user_id=admin.id, title="first", content="keep")
	db_session.add(first_note)
	await db_session.flush()
	await thread_service.create_message(
		first_thread.id,
		MessageDraft(
			content=[TextContent(text="origin")],
		),
		db_session,
		principal=principal,
		originated_resources=[
			ResourceAttachment(type=ResourceType.NOTE, id=first_note.id)
		],
	)
	with patch(
		"api.v1.service.threads.core.remove_vectorized_resource",
		new=AsyncMock(),
	):
		await thread_service.delete_thread(
			first_thread.id,
			db_session,
			principal=principal,
		)
	assert await db_session.get(Note, first_note.id) is not None

	second_thread = await thread_service.create_thread(
		ThreadCreate(owner_id=admin.id, title="thread cascade true"),
		db_session,
		principal=principal,
	)
	second_note = Note(user_id=admin.id, title="second", content="delete")
	db_session.add(second_note)
	await db_session.flush()
	await thread_service.create_message(
		second_thread.id,
		MessageDraft(
			content=[TextContent(text="origin")],
		),
		db_session,
		principal=principal,
		originated_resources=[
			ResourceAttachment(type=ResourceType.NOTE, id=second_note.id)
		],
	)
	with patch(
		"api.v1.service.threads.core.remove_vectorized_resource",
		new=AsyncMock(),
	):
		await delete_thread_with_originated_resources(
			second_thread.id,
			db_session,
			principal=principal,
		)
	stmt = (
		select(Note)
		.where(Note.id == second_note.id)
		.execution_options(include_deleted=True)
	)
	deleted_note = (await db_session.execute(stmt)).scalar_one()
	assert deleted_note.deleted_at is not None


@pytest.mark.asyncio
async def test_thread_origin_cascade_authorizes_owner_before_deleting_resources(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="thread-origin-owner@example.com",
		username="thread_origin_owner",
		hashed_password="pw",
	)
	editor = User(
		email="thread-origin-editor@example.com",
		username="thread_origin_editor",
		hashed_password="pw",
	)
	db_session.add_all([owner, editor])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="owner guard")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	db_session.add(message)
	await db_session.flush()
	note = Note(
		user_id=editor.id,
		title="must survive",
		content="origin",
		origin_message_id=message.id,
	)
	db_session.add_all(
		[
			note,
			AccessRule(
				thread_id=thread.id,
				subject_user_id=editor.id,
				level=AccessLevel.EDITOR,
			),
		]
	)
	await db_session.flush()

	with pytest.raises(HTTPException) as exc_info:
		await delete_thread_with_originated_resources(
			thread.id,
			db_session,
			principal=Principal.for_user(
				user=editor,
				group_ids=(),
				permissions=frozenset(),
			),
		)

	assert exc_info.value.status_code == 403
	assert await db_session.get(Note, note.id) is not None


@pytest.mark.asyncio
async def test_thread_origin_cascade_authorizes_permanent_delete_first(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="thread-permanent-owner@example.com",
		username="thread_permanent_owner",
		hashed_password="pw",
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="permanent guard")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	db_session.add(message)
	await db_session.flush()
	note = Note(
		user_id=owner.id,
		title="must survive",
		content="origin",
		origin_message_id=message.id,
	)
	db_session.add(note)
	await db_session.flush()

	delete_mock = AsyncMock()
	with (
		patch(
			"api.v1.service.resource_origins.deletion.delete_originated_resources",
			new=delete_mock,
		),
		pytest.raises(HTTPException) as exc_info,
	):
		await delete_thread_with_originated_resources(
			thread.id,
			db_session,
			principal=Principal.for_user(
				user=owner,
				group_ids=(),
				permissions=frozenset(),
			),
			permanent=True,
		)

	assert exc_info.value.status_code == 403
	delete_mock.assert_not_awaited()
	assert await db_session.get(Note, note.id) is not None


@pytest.mark.asyncio
async def test_message_origin_cascade_authorizes_target_before_deleting_resources(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="message-origin-owner@example.com",
		username="message_origin_owner",
		hashed_password="pw",
	)
	editor = User(
		email="message-origin-editor@example.com",
		username="message_origin_editor",
		hashed_password="pw",
	)
	db_session.add_all([owner, editor])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="message guard")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=owner.id,
	)
	db_session.add(message)
	await db_session.flush()
	note = Note(
		user_id=editor.id,
		title="must survive",
		content="origin",
		origin_message_id=message.id,
	)
	db_session.add_all(
		[
			note,
			AccessRule(
				thread_id=thread.id,
				subject_user_id=editor.id,
				level=AccessLevel.EDITOR,
			),
		]
	)
	await db_session.flush()

	with pytest.raises(HTTPException) as exc_info:
		await delete_user_message_turn_with_originated_resources(
			thread.id,
			message.id,
			db_session,
			principal=Principal.for_user(
				user=editor,
				group_ids=(),
				permissions=frozenset(),
			),
		)

	assert exc_info.value.status_code == 404
	assert await db_session.get(Note, note.id) is not None


@pytest.mark.asyncio
async def test_origin_cascade_skips_resources_caller_cannot_delete(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-skip-owner@example.com",
		username="origin_skip_owner",
		hashed_password="pw",
	)
	caller = User(
		email="origin-skip-caller@example.com",
		username="origin_skip_caller",
		hashed_password="pw",
	)
	db_session.add_all([owner, caller])
	await db_session.flush()
	note = Note(user_id=owner.id, title="cannot delete", content="keep")
	db_session.add(note)
	await db_session.flush()

	await delete_originated_resources(
		[(ResourceType.NOTE, TypeID(str(note.id)))],
		db_session,
		principal=Principal.for_user(
			user=caller,
			group_ids=(),
			permissions=frozenset(),
		),
	)

	assert await db_session.get(Note, note.id) is not None


@pytest.mark.asyncio
async def test_origin_cascade_continues_after_inaccessible_resource(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="origin-continue-owner@example.com",
		username="origin_continue_owner",
		hashed_password="pw",
	)
	caller = User(
		email="origin-continue-caller@example.com",
		username="origin_continue_caller",
		hashed_password="pw",
	)
	db_session.add_all([owner, caller])
	await db_session.flush()
	inaccessible_note = Note(
		user_id=owner.id,
		title="cannot delete",
		content="keep",
	)
	accessible_note = Note(
		user_id=caller.id,
		title="can delete",
		content="delete",
	)
	db_session.add_all([inaccessible_note, accessible_note])
	await db_session.flush()

	await delete_originated_resources(
		[
			(ResourceType.NOTE, TypeID(str(inaccessible_note.id))),
			(ResourceType.NOTE, TypeID(str(accessible_note.id))),
		],
		db_session,
		principal=Principal.for_user(
			user=caller,
			group_ids=(),
			permissions=frozenset(),
		),
	)

	assert await db_session.get(Note, inaccessible_note.id) is not None
	stmt = (
		select(Note)
		.where(Note.id == accessible_note.id)
		.execution_options(include_deleted=True)
	)
	deleted_note = (await db_session.execute(stmt)).scalar_one()
	assert deleted_note.deleted_at is not None
