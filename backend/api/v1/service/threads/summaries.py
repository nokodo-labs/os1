"""service helpers for thread summaries."""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose, ThreadSummary
from api.schemas.thread import ThreadSummaryUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_admin, require_thread_access
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


SUMMARY_COVERED_RAW_IDS_METADATA_KEY = "covered_raw_message_ids"


def latest_active_summary_text(
	thread: Thread,
	purpose: SummaryPurpose,
) -> str | None:
	"""return the newest active summary text already loaded on a thread."""
	summaries = thread.__dict__.get("summaries")
	if not isinstance(summaries, list):
		return None
	candidates = [
		summary
		for summary in summaries
		if isinstance(summary, ThreadSummary)
		and summary.purpose == purpose
		and summary.superseded_by_id is None
		and summary.content.strip()
	]
	if not candidates:
		return None
	return max(candidates, key=lambda summary: summary.created_at).content.strip()


async def create_summary(
	thread_id: TypeID,
	content: str,
	message_count: int,
	session: AsyncSession,
	start_message_id: TypeID | None = None,
	end_message_id: TypeID | None = None,
	purpose: SummaryPurpose = SummaryPurpose.AGENT_CONTEXT,
	metadata: JSONObject | None = None,
) -> ThreadSummary:
	"""create and persist a new thread summary."""
	summary = ThreadSummary(
		thread_id=thread_id,
		purpose=purpose,
		content=content,
		message_count=message_count,
		start_message_id=start_message_id,
		end_message_id=end_message_id,
		metadata_=metadata or {},
	)
	session.add(summary)
	await session.flush()
	await session.refresh(summary)
	return summary


async def list_active_summaries(
	thread_id: TypeID,
	session: AsyncSession,
	purpose: SummaryPurpose | None = None,
) -> list[ThreadSummary]:
	"""list non-superseded summaries for a thread, ordered by creation."""
	stmt = select(ThreadSummary).where(
		ThreadSummary.thread_id == thread_id,
		ThreadSummary.superseded_by_id.is_(None),
	)
	if purpose is not None:
		stmt = stmt.where(ThreadSummary.purpose == purpose)
	stmt = stmt.order_by(ThreadSummary.created_at.asc(), ThreadSummary.id.asc())
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_summaries(
	thread_id: TypeID,
	session: AsyncSession,
	include_superseded: bool = True,
	purpose: SummaryPurpose | None = None,
) -> list[ThreadSummary]:
	"""list stored summaries for a thread, ordered by creation."""
	stmt = select(ThreadSummary).where(ThreadSummary.thread_id == thread_id)
	if not include_superseded:
		stmt = stmt.where(ThreadSummary.superseded_by_id.is_(None))
	if purpose is not None:
		stmt = stmt.where(ThreadSummary.purpose == purpose)
	stmt = stmt.order_by(ThreadSummary.created_at.asc(), ThreadSummary.id.asc())
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def count_active_summaries(
	thread_id: TypeID,
	session: AsyncSession,
	purpose: SummaryPurpose | None = None,
) -> int:
	"""count non-superseded summaries for a thread."""
	inner = select(ThreadSummary.id).where(
		ThreadSummary.thread_id == thread_id,
		ThreadSummary.superseded_by_id.is_(None),
	)
	if purpose is not None:
		inner = inner.where(ThreadSummary.purpose == purpose)
	stmt = select(func.count()).select_from(inner.subquery())
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
	stmt = select(ThreadSummary).where(ThreadSummary.id.in_(summary_ids))
	result = await session.execute(stmt)
	for summary in result.scalars().all():
		summary.superseded_by_id = replacement_id
	await session.flush()


async def get_summary(
	summary_id: TypeID,
	session: AsyncSession,
	thread_id: TypeID | None = None,
) -> ThreadSummary | None:
	"""get a single summary by id, optionally scoped to a thread."""
	summary = await session.get(ThreadSummary, str(summary_id))
	if summary is None:
		return None
	if thread_id is not None and summary.thread_id != thread_id:
		return None
	return summary


async def _load_summary_for_thread(
	thread_id: TypeID,
	summary_id: TypeID,
	session: AsyncSession,
) -> ThreadSummary:
	"""load a summary scoped to a thread or raise a 404."""
	summary = await get_summary(summary_id, session, thread_id)
	if summary is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="summary not found",
		)
	return summary


async def list_thread_summaries(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_superseded: bool = False,
	purpose: SummaryPurpose | None = None,
) -> list[ThreadSummary]:
	"""list summaries visible to a principal for one thread."""
	if principal.is_admin:
		await require_thread_access(thread_id, session, principal, AccessLevel.READER)
		return await list_summaries(
			thread_id,
			session,
			include_superseded=include_superseded,
			purpose=purpose,
		)

	if purpose == SummaryPurpose.AGENT_CONTEXT:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="admin access required",
		)
	await require_thread_access(thread_id, session, principal, AccessLevel.READER)
	return await list_summaries(
		thread_id,
		session,
		include_superseded=False,
		purpose=SummaryPurpose.CATALOG,
	)


async def get_thread_summary(
	thread_id: TypeID,
	summary_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> ThreadSummary:
	"""get one summary visible to a principal for one thread."""
	summary = await _load_summary_for_thread(thread_id, summary_id, session)
	if principal.is_admin:
		return summary
	if summary.purpose == SummaryPurpose.AGENT_CONTEXT:
		require_admin(principal)
	await require_thread_access(thread_id, session, principal, AccessLevel.READER)
	return summary


async def update_thread_summary(
	thread_id: TypeID,
	summary_id: TypeID,
	summary_in: ThreadSummaryUpdate,
	session: AsyncSession,
	principal: Principal,
) -> ThreadSummary:
	"""update a stored summary. admin only."""
	require_admin(principal)
	summary = await _load_summary_for_thread(thread_id, summary_id, session)
	updates = summary_in.model_dump(exclude_unset=True, by_alias=True)
	if "content" in updates:
		summary.content = updates["content"]
	if "metadata_" in updates:
		summary.metadata_ = updates["metadata_"]
	await session.flush()
	await session.refresh(summary)
	return summary


async def delete_thread_summary(
	thread_id: TypeID,
	summary_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete a stored summary. admin only."""
	require_admin(principal)
	summary = await _load_summary_for_thread(thread_id, summary_id, session)
	await session.delete(summary)
	await session.flush()


async def delete_stale_summaries_for_thread(
	thread_id: TypeID,
	session: AsyncSession,
	purpose: SummaryPurpose | None = None,
	changed_message_ids: Iterable[TypeID | str] | None = None,
	active_end_message_id: TypeID | str | None = None,
) -> int:
	"""delete summaries made stale by branch or content mutations.

	when changed message ids are supplied, only summaries whose stored
	start/end range overlaps those messages are invalidated. summaries without
	a usable end message are treated as stale because their coverage cannot be
	proven. when an active end message is supplied, summaries ending elsewhere
	are invalidated for active-branch catalog maintenance.
	"""
	filters = [ThreadSummary.thread_id == thread_id]
	if purpose is not None:
		filters.append(ThreadSummary.purpose == purpose)
	if active_end_message_id is not None:
		filters.append(
			or_(
				ThreadSummary.end_message_id.is_(None),
				ThreadSummary.end_message_id != str(active_end_message_id),
			)
		)
	if changed_message_ids is None:
		result = await session.execute(select(ThreadSummary.id).where(*filters))
		summary_ids = [str(summary_id) for summary_id in result.scalars().all()]
	else:
		changed_ids = {str(message_id) for message_id in changed_message_ids}
		result = await session.execute(select(ThreadSummary).where(*filters))
		summary_ids = []
		for summary in result.scalars().all():
			if await _summary_overlaps_messages(summary, changed_ids, session):
				summary_ids.append(str(summary.id))
	if not summary_ids:
		return 0
	stmt = sa_delete(ThreadSummary).where(ThreadSummary.id.in_(summary_ids))
	await session.execute(stmt)
	await session.flush()
	return len(summary_ids)


async def _summary_branch_ids(
	summary: ThreadSummary,
	session: AsyncSession,
) -> list[str]:
	"""return the root-first branch ids ending at a summary's end message."""
	if summary.end_message_id is None:
		return []
	anchor = (
		select(
			Message.id.label("msg_id"),
			Message.parent_id.label("parent_id"),
			literal(0).label("depth"),
		)
		.where(Message.id == str(summary.end_message_id))
		.cte(name="summary_branch", recursive=True)
	)
	recursive = select(
		Message.id.label("msg_id"),
		Message.parent_id.label("parent_id"),
		(anchor.c.depth + 1).label("depth"),
	).join(anchor, Message.id == anchor.c.parent_id)
	branch_cte = anchor.union_all(recursive)
	stmt = select(branch_cte.c.msg_id).order_by(branch_cte.c.depth.desc())
	result = await session.execute(stmt)
	return [str(row[0]) for row in result]


async def _summary_overlaps_messages(
	summary: ThreadSummary,
	changed_ids: set[str],
	session: AsyncSession,
) -> bool:
	"""return whether a summary's covered branch span intersects changed ids."""
	covered_raw_ids = summary.metadata_.get(SUMMARY_COVERED_RAW_IDS_METADATA_KEY)
	if isinstance(covered_raw_ids, list):
		covered_ids = {
			message_id for message_id in covered_raw_ids if isinstance(message_id, str)
		}
		return bool(covered_ids & changed_ids)
	branch_ids = await _summary_branch_ids(summary, session)
	if not branch_ids:
		return True
	start_index = 0
	if summary.start_message_id is not None:
		try:
			start_index = branch_ids.index(str(summary.start_message_id))
		except ValueError:
			return True
	covered_ids = set(branch_ids[start_index:])
	return bool(covered_ids & changed_ids)
