"""tests for persisted run-steering message placement."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.user import User
from api.v1.service.chat.steering import persist_injected_steering


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

	root = Message(
		thread_id=thread.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "start"}],
		sender_user_id=user.id,
	)
	db_session.add(root)
	await db_session.flush()

	assistant = Message(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.ASSISTANT,
		content=[],
		tool_calls=[{"id": "tool_call_1", "name": "agentic_web_search"}],
	)
	db_session.add(assistant)
	await db_session.flush()

	tool = Message(
		thread_id=thread.id,
		parent_id=assistant.id,
		type=MessageType.TOOL,
		content=[{"type": "text", "text": "result"}],
		tool_call_id="tool_call_1",
		is_error=False,
	)
	queued_1 = Message(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "first steer"}],
		sender_user_id=user.id,
		metadata_={"steering_state": "queued"},
	)
	queued_2 = Message(
		thread_id=thread.id,
		parent_id=root.id,
		type=MessageType.USER,
		content=[{"type": "text", "text": "second steer"}],
		sender_user_id=user.id,
		metadata_={"steering_state": "queued"},
	)
	db_session.add_all([tool, queued_1, queued_2])
	await db_session.flush()
	thread.current_message_id = tool.id
	thread_id = thread.id
	tool_id = tool.id
	queued_1_id = queued_1.id
	queued_2_id = queued_2.id
	await db_session.commit()

	last_injected = await persist_injected_steering([queued_1_id, queued_2_id], tool_id)

	db_session.expire_all()
	stored_queued_1 = await db_session.get(Message, queued_1_id)
	stored_queued_2 = await db_session.get(Message, queued_2_id)
	stored_thread = await db_session.get(Thread, thread_id)

	assert last_injected == queued_2_id
	assert stored_queued_1 is not None
	assert stored_queued_1.parent_id == tool_id
	assert stored_queued_1.metadata_["steering_state"] == "injected"
	assert stored_queued_2 is not None
	assert stored_queued_2.parent_id == queued_1_id
	assert stored_queued_2.metadata_["steering_state"] == "injected"
	assert stored_thread is not None
	assert stored_thread.current_message_id == queued_2_id
