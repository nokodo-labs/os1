"""Tests for soft-delete behavior."""

from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread import Thread


async def _create_thread(db_session: AsyncSession, user_id: str) -> Thread:
	thread = Thread(owner_id=user_id, title="soft delete test")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)
	return thread


@pytest.mark.asyncio
async def test_thread_soft_delete_mixin(
	db_session: AsyncSession, test_user: dict
) -> None:
	thread = await _create_thread(db_session, test_user["id"])
	assert thread.is_deleted is False

	thread.soft_delete()
	assert thread.is_deleted is True
	assert thread.deleted_at is not None

	await db_session.commit()


@pytest.mark.asyncio
async def test_soft_deleted_threads_filtered_by_default(
	db_session: AsyncSession, test_user: dict
) -> None:
	thread = await _create_thread(db_session, test_user["id"])
	thread.soft_delete()
	await db_session.commit()

	# default SELECTs should hide soft-deleted rows
	result = await db_session.execute(select(Thread).where(Thread.id == thread.id))
	assert result.scalar_one_or_none() is None

	# but callers can opt-in to include deleted
	result = await db_session.execute(
		select(Thread)
		.execution_options(include_deleted=True)
		.where(Thread.id == thread.id)
	)
	assert result.scalar_one().id == thread.id

	# non-select statements should not be modified by the soft-delete criteria hook
	await db_session.execute(
		update(Thread).where(Thread.owner_id == thread.owner_id).values(title="noop")
	)
