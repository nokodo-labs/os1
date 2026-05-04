"""reminder search and vectorization helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import build_cursor_page, decode_cursor
from api.models.reminder import Reminder, ReminderList
from api.permissions import ResourceType
from api.schemas.reminder import ReminderUpdate
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
	_fields = {"title", "description", "list_id"}
	update_data = data.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


REMINDER_SPEC: VectorSpec[Reminder] = VectorSpec(
	resource_type="reminder",
	resource_id=lambda reminder: str(reminder.id),
	dense_text=_reminder_dense_text,
	bm25_text=_reminder_dense_text,
	metadata=_reminder_metadata,
	should_revectorize=_reminder_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_reminders_for_list(
	list_id: str | TypeID, session: AsyncSession
) -> None:
	"""re-vectorize all reminders in a list."""
	stmt = select(Reminder).where(Reminder.list_id == str(list_id))
	result = await session.execute(stmt)
	valid: list[tuple[Reminder, str]] = []
	for reminder in result.scalars().all():
		text = _reminder_dense_text(reminder)
		if text.strip():
			valid.append((reminder, text))
	if not valid:
		return
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (reminder, _text), embedding in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=REMINDER_SPEC,
			resource_id=str(reminder.id),
			session=session,
		)
		chunks.append(build_chunk(REMINDER_SPEC, reminder, embedding))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)


async def vectorize_all_reminders(session: AsyncSession) -> int:
	"""vectorize all reminders in bulk. returns count."""
	stmt = select(Reminder)
	result = await session.execute(stmt)
	valid: list[tuple[Reminder, str]] = []
	for reminder in result.scalars().all():
		text = _reminder_dense_text(reminder)
		if text.strip():
			valid.append((reminder, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	chunks = []
	for (reminder, _text), embedding in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=REMINDER_SPEC,
			resource_id=str(reminder.id),
			session=session,
		)
		chunks.append(build_chunk(REMINDER_SPEC, reminder, embedding))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_reminders(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for reminders on title/description/list."""
	pattern = contains_pattern(q)
	stmt = (
		select(Reminder)
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(
			or_(
				func.similarity(Reminder.title, q) > 0.1,
				Reminder.title.ilike(pattern, escape="\\"),
				Reminder.description.ilike(pattern, escape="\\"),
				ReminderList.name.ilike(pattern, escape="\\"),
			),
		)
		.order_by(func.similarity(Reminder.title, q).desc())
		.limit(limit)
	)
	list_access = resource_access_predicate(principal, ResourceType.REMINDER_LIST)
	stmt = stmt.where(
		or_(
			Reminder.owner_id == principal.user_id,
			list_access,
		)
	)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.REMINDER,
			id=TypeID(reminder.id),
			title=reminder.title or "",
			preview=(reminder.description[:100] if reminder.description else None),
			metadata=_reminder_metadata(reminder),
			created_at=reminder.created_at,
			updated_at=reminder.updated_at,
		)
		for reminder in result.scalars().all()
	]


async def _hybrid_search_reminders(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for reminders."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (await embed_text(text=query_text, session=db) if need_dense else None)
	)
	text_query = query_text if need_sparse else None
	query_filter = vectorstore_service.resource_filter("reminder")
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	resource_ids = [str(result.metadata["resource_id"]) for result in results]
	stmt = (
		select(Reminder)
		.outerjoin(ReminderList, Reminder.list_id == ReminderList.id)
		.where(Reminder.id.in_(resource_ids))
	)
	list_access = resource_access_predicate(principal, ResourceType.REMINDER_LIST)
	stmt = stmt.where(
		or_(
			Reminder.owner_id == principal.user_id,
			list_access,
		)
	)
	db_result = await db.execute(stmt)
	by_id = {str(reminder.id): reminder for reminder in db_result.scalars().all()}
	score_by_rid = {
		str(result.metadata["resource_id"]): result.score for result in results
	}
	items: list[SearchResultItem] = []
	for result in results:
		resource_id = str(result.metadata["resource_id"])
		reminder = by_id.get(resource_id)
		if not reminder:
			continue
		items.append(
			SearchResultItem(
				type=SearchResultType.REMINDER,
				id=TypeID(reminder.id),
				title=reminder.title or "",
				preview=(reminder.description[:100] if reminder.description else None),
				score=score_by_rid.get(resource_id),
				metadata=_reminder_metadata(reminder),
				created_at=reminder.created_at,
				updated_at=reminder.updated_at,
			)
		)
	return items


async def search_reminders(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> CursorPage[SearchResultItem]:
	"""parallel pg_trgm + qdrant hybrid search with cursor pagination."""
	params = search_params or SearchParams()
	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
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
	if run_hybrid:
		coros.append(
			_hybrid_search_reminders(
				query_text,
				db,
				principal=principal,
				limit=limit + 1,
				search_params=params,
				query_embedding=query_embedding,
			)
		)
	if run_autocomplete:
		coros.append(
			_autocomplete_reminders(
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
		resource_name="reminders",
	)
	if cursor:
		timestamp, cursor_id = decode_cursor(cursor)
		sort_key = REMINDER_SPEC.sort_key
		items = [
			item
			for item in items
			if (getattr(item, sort_key), str(item.id)) < (timestamp, cursor_id)
		]
	sort_key = REMINDER_SPEC.sort_key
	items.sort(key=lambda item: (getattr(item, sort_key), str(item.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=REMINDER_SPEC.sort_key)
