"""PostgreSQL-native recursive CTE cycle tests."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType, UserMessage
from api.models.thread import Thread
from api.models.user import User
from api.v1.service.threads.tree import branch_depths_cte, selected_message_ids_cte
from nokodo_ai.utils.typeid import new_typeid


async def _cycle(session: AsyncSession) -> tuple[Thread, Message, Message]:
	user = User(
		email=f"cycle-{new_typeid('user')}@example.com",
		username=f"cycle_{new_typeid('user')[-12:]}",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
	)
	thread = Thread(owner=user, title="cycle")
	first = UserMessage(
		thread=thread,
		type=MessageType.USER,
		content=[{"type": "text", "text": "first"}],
		sender_user=user,
	)
	second = UserMessage(
		thread=thread,
		parent=first,
		type=MessageType.USER,
		content=[{"type": "text", "text": "second"}],
		sender_user=user,
	)
	session.add_all([user, thread, first, second])
	await session.flush()
	first.parent_id = second.id
	thread.current_message_id = second.id
	await session.flush()
	return thread, first, second


@pytest.mark.asyncio
async def test_branch_cte_terminates_and_excludes_cycle_row(
	db_session: AsyncSession,
) -> None:
	_thread, first, second = await _cycle(db_session)
	branch = branch_depths_cte(second.id)
	rows = list(await db_session.scalars(select(branch.c.msg_id)))
	assert rows == [second.id, first.id]


@pytest.mark.asyncio
async def test_selected_message_cte_terminates_on_cycle(
	db_session: AsyncSession,
) -> None:
	thread, first, second = await _cycle(db_session)
	selected = selected_message_ids_cte([thread.id])
	rows = set(await db_session.scalars(select(selected.c.m_id)))
	assert rows == {first.id, second.id}
