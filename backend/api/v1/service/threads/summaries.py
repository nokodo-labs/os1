"""service helpers for thread summaries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import SummaryType, ThreadSummary
from nokodo_ai.utils.typeid import TypeID


async def create_summary(
	thread_id: TypeID,
	summary_type: SummaryType,
	content: str,
	message_count: int,
	session: AsyncSession,
	start_message_id: TypeID | None = None,
	end_message_id: TypeID | None = None,
) -> ThreadSummary:
	"""create and persist a new thread summary."""
	summary = ThreadSummary(
		thread_id=thread_id,
		type=summary_type,
		content=content,
		message_count=message_count,
		start_message_id=start_message_id,
		end_message_id=end_message_id,
	)
	session.add(summary)
	await session.flush()
	await session.refresh(summary)
	return summary


async def list_active_summaries(
	thread_id: TypeID,
	session: AsyncSession,
) -> list[ThreadSummary]:
	"""list all non-superseded summaries for a thread, ordered by creation."""
	stmt = (
		select(ThreadSummary)
		.where(
			ThreadSummary.thread_id == thread_id,
			ThreadSummary.superseded_by_id.is_(None),
		)
		.order_by(ThreadSummary.created_at.asc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_summaries(
	thread_id: TypeID,
	session: AsyncSession,
	include_superseded: bool = True,
) -> list[ThreadSummary]:
	"""list stored summaries for a thread, ordered by creation."""
	stmt = select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
	if not include_superseded:
		stmt = stmt.where(ThreadSummary.superseded_by_id.is_(None))
	stmt = stmt.order_by(ThreadSummary.created_at.asc(), ThreadSummary.id.asc())
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def count_active_summaries(
	thread_id: TypeID,
	session: AsyncSession,
) -> int:
	"""count non-superseded summaries for a thread."""
	stmt = select(func.count()).select_from(
		select(ThreadSummary.id)
		.where(
			ThreadSummary.thread_id == thread_id,
			ThreadSummary.superseded_by_id.is_(None),
		)
		.subquery()
	)
	result = await session.execute(stmt)
	return result.scalar_one()


async def supersede_summaries(
	summary_ids: list[TypeID],
	replacement_id: TypeID,
	session: AsyncSession,
) -> None:
	"""mark summaries as superseded by a new condensed summary."""
	if not summary_ids:
		return
	stmt = select(ThreadSummary).where(
		ThreadSummary.id.in_([str(sid) for sid in summary_ids])
	)
	result = await session.execute(stmt)
	for summary in result.scalars().all():
		summary.superseded_by_id = replacement_id
	await session.flush()


async def get_summary(
	summary_id: TypeID,
	session: AsyncSession,
) -> ThreadSummary | None:
	"""get a single summary by ID."""
	return await session.get(ThreadSummary, str(summary_id))
