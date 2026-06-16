"""reminder search and vectorization helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.database.main import session_scope
from api.models.reminder import Reminder, ReminderList
from api.permissions import ResourceType
from api.schemas.reminder import ReminderSearchFilters, ReminderUpdate
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResourceReferenceType,
	SearchResultItem,
	SearchResultParent,
	SearchResultType,
)
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.embeddings import embed_text
from api.v1.service.search.primitives import ScoredResult, merge_scored
from api.v1.service.vectorize import (
	VectorSpec,
	vectorize_resources,
)
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.types import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


def _reminder_dense_text(reminder: Reminder) -> str:
	parts = [reminder.title or ""]
	if reminder.description:
		parts.append(reminder.description)
	return " ".join(p for p in parts if p).strip()


def _reminder_metadata(reminder: Reminder) -> JSONObject:
	return {
		"list_id": str(reminder.list_id),
		"parent_id": str(reminder.parent_id) if reminder.parent_id else None,
		"due_at": reminder.due_at.isoformat() if reminder.due_at else None,
		"remind_at": reminder.remind_at.isoformat() if reminder.remind_at else None,
		"status": reminder.status.value,
		"scheduled_source": "master",
		"owner_id": str(reminder.owner_id),
		"series_origin_id": str(reminder.series_origin_id)
		if reminder.series_origin_id
		else None,
	}


async def _reminder_should_revectorize(
	reminder: Reminder,
	data: ReminderUpdate,
	session: AsyncSession,
) -> bool:
	_fields = {
		"title",
		"description",
		"list_id",
		"parent_id",
		"due_at",
		"remind_at",
		"status",
	}
	update_data = data.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


def reminder_to_search_item(
	reminder: Reminder, score: float | None = None
) -> SearchResultItem:
	"""projection from a reminder (and optional score) to a SearchResultItem."""
	return SearchResultItem(
		type=SearchResultType.REMINDER,
		id=TypeID(reminder.id),
		title=reminder.title or "",
		preview=(reminder.description[:100] if reminder.description else None),
		score=score,
		parent=SearchResultParent(
			type=SearchResourceReferenceType.REMINDER_LIST,
			id=TypeID(reminder.list_id),
		),
		metadata=_reminder_metadata(reminder),
		created_at=reminder.created_at,
		updated_at=reminder.updated_at,
	)


REMINDER_SPEC: VectorSpec[Reminder] = VectorSpec(
	resource_type=VectorChunkResourceType.REMINDER,
	resource_id=lambda reminder: str(reminder.id),
	dense_text=_reminder_dense_text,
	bm25_text=_reminder_dense_text,
	metadata=_reminder_metadata,
	should_revectorize=_reminder_should_revectorize,
)


async def vectorize_reminders_for_list(
	list_id: str | TypeID, session: AsyncSession
) -> None:
	"""re-vectorize all reminders in a list."""
	stmt = select(Reminder).where(Reminder.list_id == str(list_id))
	result = await session.execute(stmt)
	await vectorize_resources(
		spec=REMINDER_SPEC,
		resources=list(result.scalars().all()),
		session=session,
	)


async def vectorize_all_reminders(session: AsyncSession) -> int:
	"""vectorize all reminders in bulk. returns count."""
	stmt = select(Reminder)
	result = await session.execute(stmt)
	return await vectorize_resources(
		spec=REMINDER_SPEC,
		resources=list(result.scalars().all()),
		session=session,
	)


def _reminder_search_conditions(
	filters: ReminderSearchFilters | None,
) -> list[vectorstore_service.FieldCondition]:
	"""vector-layer narrowing conditions derived from reminder search filters."""
	conditions: list[vectorstore_service.FieldCondition] = []
	if filters is None:
		return conditions
	if filters.owner_id is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="owner_id", value=str(filters.owner_id))
		)
	if filters.list_id is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="list_id", value=str(filters.list_id))
		)
	if filters.status is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="status", value=filters.status.value)
		)
	if filters.due_after is not None or filters.due_before is not None:
		conditions.append(
			vectorstore_service.FieldRange(
				key="due_at",
				gte=filters.due_after.isoformat() if filters.due_after else None,
				lte=filters.due_before.isoformat() if filters.due_before else None,
			)
		)
	if filters.remind_after is not None or filters.remind_before is not None:
		conditions.append(
			vectorstore_service.FieldRange(
				key="remind_at",
				gte=filters.remind_after.isoformat() if filters.remind_after else None,
				lte=filters.remind_before.isoformat()
				if filters.remind_before
				else None,
			)
		)
	return conditions


def _apply_reminder_search_filters(
	stmt: Select,
	filters: ReminderSearchFilters | None,
) -> Select:
	"""SQL-layer narrowing mirroring _reminder_search_conditions."""
	if filters is None:
		return stmt
	if filters.owner_id is not None:
		stmt = stmt.where(Reminder.owner_id == filters.owner_id)
	if filters.list_id is not None:
		stmt = stmt.where(Reminder.list_id == str(filters.list_id))
	if filters.status is not None:
		stmt = stmt.where(Reminder.status == filters.status)
	if filters.due_after is not None:
		stmt = stmt.where(Reminder.due_at >= filters.due_after)
	if filters.due_before is not None:
		stmt = stmt.where(Reminder.due_at <= filters.due_before)
	if filters.remind_after is not None:
		stmt = stmt.where(Reminder.remind_at >= filters.remind_after)
	if filters.remind_before is not None:
		stmt = stmt.where(Reminder.remind_at <= filters.remind_before)
	return stmt


async def _autocomplete_reminders(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: ReminderSearchFilters | None = None,
) -> list[ScoredResult[Reminder]]:
	"""pg_trgm autocomplete tier scored by title similarity."""
	pattern = contains_pattern(q)
	sim = func.similarity(Reminder.title, q)
	stmt = (
		select(Reminder, sim.label("sim"))
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(
			or_(
				sim > 0.1,
				Reminder.title.ilike(pattern, escape="\\"),
				Reminder.description.ilike(pattern, escape="\\"),
				ReminderList.name.ilike(pattern, escape="\\"),
			),
		)
		.where(resource_access_predicate(principal, ResourceType.REMINDER_LIST))
		.order_by(sim.desc())
		.offset(offset)
		.limit(limit)
	)
	stmt = _apply_reminder_search_filters(stmt, filters)
	result = await db.execute(stmt)
	return [
		ScoredResult(item=reminder, score=float(score))
		for reminder, score in result.all()
	]


async def _hybrid_search_reminders(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: ReminderSearchFilters | None = None,
) -> list[ScoredResult[Reminder]]:
	"""qdrant hybrid tier (dense + BM25), scored by fused rank."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (
			await embed_text(text=query_text, session=db, input_type="query")
			if need_dense
			else None
		)
	)
	text_query = query_text if need_sparse else None
	# reminder access is inherited from the parent list (not on the chunk), so
	# the vector layer only narrows by resource type + structured filters; the
	# SQL leg below is the authoritative ACL gate.
	query_filter = vectorstore_service.with_conditions(
		vectorstore_service.resource_types_filter([VectorChunkResourceType.REMINDER]),
		_reminder_search_conditions(filters),
	)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
		group_by="resource_id",
	)
	if not results:
		return []
	resource_ids = [str(result.metadata["resource_id"]) for result in results]
	stmt = (
		select(Reminder)
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(Reminder.id.in_(resource_ids))
		.where(resource_access_predicate(principal, ResourceType.REMINDER_LIST))
	)
	stmt = _apply_reminder_search_filters(stmt, filters)
	db_result = await db.execute(stmt)
	by_id = {str(reminder.id): reminder for reminder in db_result.scalars().all()}
	scored: list[ScoredResult[Reminder]] = []
	for result in results:
		reminder = by_id.get(str(result.metadata["resource_id"]))
		if reminder is None:
			continue
		scored.append(ScoredResult(item=reminder, score=result.score))
	return scored


async def search_reminders(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	offset: int = 0,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: ReminderSearchFilters | None = None,
	score_threshold: float = 0.0,
) -> list[ScoredResult[Reminder]]:
	"""relevance-ordered, deduped reminder hits with internal scores.

	hybrid tier ranks first; autocomplete-only matches are appended.
	"""
	params = search_params or SearchParams()
	if params.mode == SearchMode.AUTOCOMPLETE:
		return await _autocomplete_reminders(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
	fetch = offset + limit
	coros: list[Coroutine[None, None, list[ScoredResult[Reminder]]]] = []
	run_autocomplete = params.mode in (
		SearchMode.AUTOCOMPLETE,
		SearchMode.FULL,
	)
	run_hybrid = params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	)

	async def _run_hybrid() -> list[ScoredResult[Reminder]]:
		async with session_scope(None) as s:
			return await _hybrid_search_reminders(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				search_params=params,
				query_embedding=query_embedding,
				filters=filters,
			)

	async def _run_autocomplete() -> list[ScoredResult[Reminder]]:
		async with session_scope(None) as s:
			return await _autocomplete_reminders(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				filters=filters,
			)

	if run_hybrid:
		coros.append(_run_hybrid())
	if run_autocomplete:
		coros.append(_run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="reminders")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]
