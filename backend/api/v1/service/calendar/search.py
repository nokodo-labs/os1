"""calendar event search and vectorization helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.database.main import session_scope
from api.models.calendar import Calendar, CalendarEvent
from api.permissions import ResourceType
from api.schemas.calendar import CalendarEventSearchFilters, CalendarEventUpdate
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


def _calendar_event_dense_text(calendar_event: CalendarEvent) -> str:
	parts = [calendar_event.title or ""]
	if calendar_event.description:
		parts.append(calendar_event.description)
	if calendar_event.location:
		parts.append(calendar_event.location)
	if calendar_event.virtual_url:
		parts.append(calendar_event.virtual_url)
	return " ".join(part for part in parts if part).strip()


def _calendar_event_metadata(calendar_event: CalendarEvent) -> JSONObject:
	return {
		"resource_type": VectorChunkResourceType.CALENDAR_EVENT.value,
		"scheduled_kind": "event",
		"scheduled_source": "master",
		"owner_id": str(calendar_event.owner_id),
		"calendar_id": str(calendar_event.calendar_id),
		"title": calendar_event.title or "",
		"start_at": calendar_event.start_at.isoformat(),
		"end_at": calendar_event.end_at.isoformat(),
		"is_recurring": calendar_event.recurrence is not None,
		"recurrence_until": calendar_event.recurrence_until.isoformat()
		if calendar_event.recurrence_until
		else None,
		"series_origin_id": str(calendar_event.series_origin_id)
		if calendar_event.series_origin_id
		else None,
	}


async def _calendar_event_should_revectorize(
	calendar_event: CalendarEvent,
	data: CalendarEventUpdate,
	session: AsyncSession,
) -> bool:
	_fields = {
		"title",
		"description",
		"start_at",
		"end_at",
		"recurrence",
		"location",
		"virtual_url",
	}
	update_data = data.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


def calendar_event_to_search_item(
	calendar_event: CalendarEvent, score: float | None = None
) -> SearchResultItem:
	"""projection from a calendar event (and optional score) to a SearchResultItem."""
	return SearchResultItem(
		type=SearchResultType.CALENDAR_EVENT,
		id=TypeID(calendar_event.id),
		title=calendar_event.title or "",
		preview=calendar_event.description[:100]
		if calendar_event.description
		else None,
		score=score,
		parent=SearchResultParent(
			type=SearchResourceReferenceType.CALENDAR,
			id=TypeID(calendar_event.calendar_id),
		),
		metadata=_calendar_event_metadata(calendar_event),
		created_at=calendar_event.created_at,
		updated_at=calendar_event.updated_at,
	)


CALENDAR_EVENT_SPEC: VectorSpec[CalendarEvent] = VectorSpec(
	resource_type=VectorChunkResourceType.CALENDAR_EVENT,
	resource_id=lambda calendar_event: str(calendar_event.id),
	dense_text=_calendar_event_dense_text,
	bm25_text=_calendar_event_dense_text,
	metadata=_calendar_event_metadata,
	should_revectorize=_calendar_event_should_revectorize,
)


async def vectorize_calendar_events_for_calendar(
	calendar_id: str | TypeID,
	session: AsyncSession,
) -> None:
	"""re-vectorize all events in a calendar."""
	stmt = (
		select(CalendarEvent)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			CalendarEvent.calendar_id == str(calendar_id),
		)
	)
	result = await session.execute(stmt)
	await vectorize_resources(
		spec=CALENDAR_EVENT_SPEC,
		resources=list(result.scalars().all()),
		session=session,
	)


async def vectorize_all_calendar_events(session: AsyncSession) -> int:
	"""vectorize all calendar events in bulk. returns count."""
	stmt = select(CalendarEvent).join(
		Calendar, CalendarEvent.calendar_id == Calendar.id
	)
	result = await session.execute(stmt)
	return await vectorize_resources(
		spec=CALENDAR_EVENT_SPEC,
		resources=list(result.scalars().all()),
		session=session,
	)


def _apply_calendar_event_search_filters(
	stmt: Select, filters: CalendarEventSearchFilters | None
) -> Select:
	"""narrow a calendar event select by the time window in search filters."""
	if filters is None:
		return stmt
	if filters.start_at is not None:
		stmt = stmt.where(CalendarEvent.end_at >= filters.start_at)
	if filters.end_at is not None:
		stmt = stmt.where(CalendarEvent.start_at <= filters.end_at)
	return stmt


async def _autocomplete_calendar_events(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: CalendarEventSearchFilters | None = None,
) -> list[ScoredResult[CalendarEvent]]:
	"""pg_trgm autocomplete tier scored by title similarity."""
	pattern = contains_pattern(q)
	sim = func.similarity(CalendarEvent.title, q)
	stmt = (
		select(CalendarEvent, sim.label("sim"))
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			resource_access_predicate(principal, ResourceType.CALENDAR),
			or_(
				sim > 0.1,
				CalendarEvent.title.ilike(pattern, escape="\\"),
				CalendarEvent.description.ilike(pattern, escape="\\"),
				CalendarEvent.location.ilike(pattern, escape="\\"),
				CalendarEvent.virtual_url.ilike(pattern, escape="\\"),
			),
		)
		.order_by(sim.desc())
		.offset(offset)
		.limit(limit)
	)
	stmt = _apply_calendar_event_search_filters(stmt, filters)
	result = await db.execute(stmt)
	return [
		ScoredResult(item=calendar_event, score=float(score))
		for calendar_event, score in result.all()
	]


async def _hybrid_search_calendar_events(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: CalendarEventSearchFilters | None = None,
) -> list[ScoredResult[CalendarEvent]]:
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
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=vectorstore_service.resource_types_filter(
			[VectorChunkResourceType.CALENDAR_EVENT]
		),
		normalize=params.normalize,
		group_by="resource_id",
	)
	if not results:
		return []
	resource_ids = [str(result.metadata["resource_id"]) for result in results]
	stmt = (
		select(CalendarEvent)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			CalendarEvent.id.in_(resource_ids),
			resource_access_predicate(principal, ResourceType.CALENDAR),
		)
	)
	stmt = _apply_calendar_event_search_filters(stmt, filters)
	db_result = await db.execute(stmt)
	by_id = {
		str(calendar_event.id): calendar_event
		for calendar_event in db_result.scalars().all()
	}
	scored: list[ScoredResult[CalendarEvent]] = []
	for result in results:
		calendar_event = by_id.get(str(result.metadata["resource_id"]))
		if calendar_event is None:
			continue
		scored.append(ScoredResult(item=calendar_event, score=result.score))
	return scored


async def search_calendar_events(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	offset: int = 0,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	score_threshold: float = 0.0,
	filters: CalendarEventSearchFilters | None = None,
) -> list[ScoredResult[CalendarEvent]]:
	"""relevance-ordered, deduped calendar event hits with internal scores.

	hybrid tier ranks first; autocomplete-only matches are appended.
	"""
	params = search_params or SearchParams()
	if params.mode == SearchMode.AUTOCOMPLETE:
		return await _autocomplete_calendar_events(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
	fetch = offset + limit
	coros: list[Coroutine[None, None, list[ScoredResult[CalendarEvent]]]] = []

	async def _run_hybrid() -> list[ScoredResult[CalendarEvent]]:
		async with session_scope(None) as s:
			return await _hybrid_search_calendar_events(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				search_params=params,
				query_embedding=query_embedding,
				filters=filters,
			)

	async def _run_autocomplete() -> list[ScoredResult[CalendarEvent]]:
		async with session_scope(None) as s:
			return await _autocomplete_calendar_events(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				filters=filters,
			)

	if params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	):
		coros.append(_run_hybrid())
	if params.mode in (SearchMode.AUTOCOMPLETE, SearchMode.FULL):
		coros.append(_run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="calendar events")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]
