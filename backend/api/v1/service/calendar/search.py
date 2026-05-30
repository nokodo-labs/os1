"""calendar event search and vectorization helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import build_cursor_page, decode_cursor
from api.models.calendar import Calendar, CalendarEvent
from api.permissions import ResourceType
from api.schemas.calendar import CalendarEventUpdate
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import resource_access_predicate
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	remove_vectorized_resource,
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


CALENDAR_EVENT_SPEC: VectorSpec[CalendarEvent] = VectorSpec(
	resource_type=VectorChunkResourceType.CALENDAR_EVENT,
	resource_id=lambda calendar_event: str(calendar_event.id),
	dense_text=_calendar_event_dense_text,
	bm25_text=_calendar_event_dense_text,
	metadata=_calendar_event_metadata,
	should_revectorize=_calendar_event_should_revectorize,
	sort_key="updated_at",
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
	valid: list[tuple[CalendarEvent, str]] = []
	for calendar_event in result.scalars().all():
		text = _calendar_event_dense_text(calendar_event)
		if text.strip():
			valid.append((calendar_event, text))
	if not valid:
		return
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (calendar_event, _text), embedding in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=CALENDAR_EVENT_SPEC,
			resource_id=str(calendar_event.id),
			session=session,
		)
		chunks.append(build_chunk(CALENDAR_EVENT_SPEC, calendar_event, embedding))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)


async def vectorize_all_calendar_events(session: AsyncSession) -> int:
	"""vectorize all calendar events in bulk. returns count."""
	stmt = select(CalendarEvent).join(
		Calendar, CalendarEvent.calendar_id == Calendar.id
	)
	result = await session.execute(stmt)
	valid: list[tuple[CalendarEvent, str]] = []
	for calendar_event in result.scalars().all():
		text = _calendar_event_dense_text(calendar_event)
		if text.strip():
			valid.append((calendar_event, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (calendar_event, _text), embedding in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=CALENDAR_EVENT_SPEC,
			resource_id=str(calendar_event.id),
			session=session,
		)
		chunks.append(build_chunk(CALENDAR_EVENT_SPEC, calendar_event, embedding))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_calendar_events(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for calendar events."""
	pattern = contains_pattern(q)
	stmt = (
		select(CalendarEvent)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			resource_access_predicate(principal, ResourceType.CALENDAR),
			or_(
				func.similarity(CalendarEvent.title, q) > 0.1,
				CalendarEvent.title.ilike(pattern, escape="\\"),
				CalendarEvent.description.ilike(pattern, escape="\\"),
				CalendarEvent.location.ilike(pattern, escape="\\"),
				CalendarEvent.virtual_url.ilike(pattern, escape="\\"),
			),
		)
		.order_by(func.similarity(CalendarEvent.title, q).desc())
		.limit(limit)
	)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.CALENDAR_EVENT,
			id=TypeID(calendar_event.id),
			title=calendar_event.title or "",
			preview=calendar_event.description[:100]
			if calendar_event.description
			else None,
			metadata=_calendar_event_metadata(calendar_event),
			created_at=calendar_event.created_at,
			updated_at=calendar_event.updated_at,
		)
		for calendar_event in result.scalars().all()
	]


async def _hybrid_search_calendar_events(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for calendar events."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (await embed_text(text=query_text, session=db) if need_dense else None)
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
	db_result = await db.execute(stmt)
	by_id = {
		str(calendar_event.id): calendar_event
		for calendar_event in db_result.scalars().all()
	}
	score_by_id = {
		str(result.metadata["resource_id"]): result.score for result in results
	}
	items: list[SearchResultItem] = []
	for result in results:
		resource_id = str(result.metadata["resource_id"])
		calendar_event = by_id.get(resource_id)
		if calendar_event is None:
			continue
		items.append(
			SearchResultItem(
				type=SearchResultType.CALENDAR_EVENT,
				id=TypeID(calendar_event.id),
				title=calendar_event.title or "",
				preview=calendar_event.description[:100]
				if calendar_event.description
				else None,
				score=score_by_id.get(resource_id),
				metadata=_calendar_event_metadata(calendar_event),
				created_at=calendar_event.created_at,
				updated_at=calendar_event.updated_at,
			)
		)
	return items


async def search_calendar_events(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> CursorPage[SearchResultItem]:
	"""parallel pg_trgm + qdrant search for calendar events."""
	params = search_params or SearchParams()
	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	if params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	):
		coros.append(
			_hybrid_search_calendar_events(
				query_text,
				db,
				principal=principal,
				limit=limit + 1,
				search_params=params,
				query_embedding=query_embedding,
			)
		)
	if params.mode in (SearchMode.AUTOCOMPLETE, SearchMode.FULL):
		coros.append(
			_autocomplete_calendar_events(
				query_text,
				db,
				principal=principal,
				limit=limit + 1,
			)
		)
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results,
		limit + 1,
		resource_name="calendar events",
	)
	if cursor:
		timestamp, cursor_id = decode_cursor(cursor)
		items = [
			item
			for item in items
			if (item.updated_at, str(item.id)) < (timestamp, cursor_id)
		]
	items.sort(key=lambda item: (item.updated_at, str(item.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=CALENDAR_EVENT_SPEC.sort_key)
