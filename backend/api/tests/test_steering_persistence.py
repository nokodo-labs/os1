"""tests for persisted run-steering message placement."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import (
	AssistantMessage,
	Message,
	MessageType,
	ToolMessage,
	UserMessage,
)
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import TextContent
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.chat.message_metadata import (
	STEERING_ENQUEUED_AT_KEY,
	STEERING_INJECTED_AT_KEY,
)
from api.v1.service.runs.steering import persist_injected_steering
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.utils.typeid import TypeID


pytestmark = pytest.mark.asyncio


async def test_persist_injected_steering_reparents_in_order(
	db_session: AsyncSession,
) -> None:
	"""injected steering messages persist where the agent consumed them."""
	user = User(
		email="steering@example.com",
		username="steering",
		hashed_password="x",
	)
	db_session.add(user)
	await db_session.flush()

	thread = Thread(title="steering", owner_id=user.id)
	db_session.add(thread)
	await db_session.flush()

	root = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "start"}],
		sender_user_id=user.id,
	)
	db_session.add(root)
	await db_session.flush()

	assistant = AssistantMessage(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.ASSISTANT,
		content=[],
		tool_calls=[{"id": "tool_call_1", "name": "agentic_web_search"}],
	)
	db_session.add(assistant)
	await db_session.flush()

	tool = ToolMessage(
		thread_id=thread.id,
		parent_id=assistant.id,
		type=MessageType.TOOL,
		content=[{"type": "text", "text": "result"}],
		tool_call_id="tool_call_1",
		is_error=False,
	)
	enqueued_at = datetime(2026, 5, 16, 12, 0, tzinfo=UTC).isoformat()
	queued_1 = UserMessage(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "first steer"}],
		sender_user_id=user.id,
		metadata_={"steering_state": "queued", STEERING_ENQUEUED_AT_KEY: enqueued_at},
	)
	queued_2 = UserMessage(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "second steer"}],
		sender_user_id=user.id,
		metadata_={"steering_state": "queued", STEERING_ENQUEUED_AT_KEY: enqueued_at},
	)
	db_session.add_all([tool, queued_1, queued_2])
	await db_session.flush()
	thread.current_message_id = tool.id
	thread_id = thread.id
	tool_id = tool.id
	queued_1_id = queued_1.id
	queued_2_id = queued_2.id
	await db_session.commit()

	consumed_at = datetime(2026, 5, 16, 12, 30, tzinfo=UTC)
	injected = await persist_injected_steering(
		[queued_1_id, queued_2_id],
		tool_id,
		TypeID(str(thread_id)),
		principal=Principal.for_user(
			user=user,
			group_ids=(),
			permissions=frozenset(),
		),
		consumed_at=consumed_at,
	)

	db_session.expire_all()
	stored_queued_1 = await db_session.get(Message, queued_1_id)
	stored_queued_2 = await db_session.get(Message, queued_2_id)
	stored_thread = await db_session.get(Thread, thread_id)

	assert injected == [queued_1_id, queued_2_id]
	assert stored_queued_1 is not None
	assert stored_queued_1.parent_id == tool_id
	assert stored_queued_1.created_at == consumed_at
	assert stored_queued_1.updated_at == consumed_at
	assert stored_queued_1.metadata_["steering_state"] == "injected"
	assert stored_queued_1.metadata_[STEERING_ENQUEUED_AT_KEY] == enqueued_at
	assert (
		stored_queued_1.metadata_[STEERING_INJECTED_AT_KEY] == consumed_at.isoformat()
	)
	assert stored_queued_2 is not None
	assert stored_queued_2.parent_id == queued_1_id
	assert stored_queued_2.created_at == consumed_at
	assert stored_queued_2.updated_at == consumed_at
	assert stored_queued_2.metadata_["steering_state"] == "injected"
	assert stored_queued_2.metadata_[STEERING_ENQUEUED_AT_KEY] == enqueued_at
	assert (
		stored_queued_2.metadata_[STEERING_INJECTED_AT_KEY] == consumed_at.isoformat()
	)
	assert stored_thread is not None
	assert stored_thread.current_message_id == queued_2_id


async def test_queued_steering_does_not_move_the_head(
	db_session: AsyncSession,
) -> None:
	"""a queued steering row exists so clients can render it, but the agent has
	not read it - so the conversation must still end where it did.

	the write itself must leave the head alone. moving it and rewinding
	afterwards leaves a window where another writer chains onto a message
	nobody has seen, and the rewind then strands that writer off canon.
	"""
	user = User(
		email="queuedhead@example.com",
		username="queuedhead",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
	)
	db_session.add(user)
	await db_session.flush()

	thread = Thread(owner_id=user.id, title="queued head")
	db_session.add(thread)
	await db_session.flush()

	root = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "hello"}],
		sender_user_id=user.id,
	)
	db_session.add(root)
	await db_session.flush()
	thread.current_message_id = root.id
	root_id = root.id
	thread_id = thread.id
	await db_session.commit()

	queued = await thread_service.create_message(
		TypeID(str(thread_id)),
		MessageDraft(
			content=[TextContent(text="wait, use staging")],
			type=MessageType.USER,
			sender_user_id=TypeID(str(user.id)),
		),
		db_session,
		principal=Principal.for_user(user=user, group_ids=(), permissions=frozenset()),
		advances_head=False,
	)

	assert str(queued.message.parent_id) == str(root_id)
	stored_thread = await db_session.get(Thread, thread_id)
	assert stored_thread is not None
	assert str(stored_thread.current_message_id) == str(root_id)
