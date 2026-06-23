"""service helpers for threads and messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.database.main import session_scope
from api.models.access_rule import AccessLevel
from api.models.message import MessageType
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose
from api.permissions import ResourceType
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.schemas.thread import ThreadSearchFilters, ThreadUpdate
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	fetch_bulk_acl_metadata,
	resource_access_predicate,
	vector_acl_filter,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.search.primitives import ScoredResult, merge_scored
from api.v1.service.threads.summaries import latest_active_summary_text
from api.v1.service.vectorize import (
	VectorSpec,
	vectorize_resources,
)
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _thread_dense_text(thread: Thread) -> str:
	"""build dense vector text from title plus latest catalog summary."""
	parts: list[str] = []
	if thread.title:
		parts.append(thread.title)
	summary = latest_active_summary_text(
		thread,
		SummaryPurpose.CATALOG,
	)
	if summary is None:
		summary = (thread.metadata_ or {}).get("summary")
	if summary:
		parts.append(str(summary))
	return " ".join(parts).strip()


def _thread_bm25_text(thread: Thread) -> str:
	"""build sparse search text from dense fields plus visible message text."""
	dense = _thread_dense_text(thread)
	parts = [dense] if dense else []
	if thread.messages:
		msg_text = " ".join(
			m.text_content
			for m in thread.messages
			if m.type in (MessageType.USER, MessageType.ASSISTANT) and m.text_content
		)
		if msg_text:
			parts.append(msg_text)
	return " ".join(parts).strip()


def _thread_metadata(thread: Thread) -> JSONObject:
	"""build vector metadata for a thread resource."""
	return {
		"resource_type": VectorChunkResourceType.THREAD.value,
		"owner_id": str(thread.owner_id),
		"title": thread.title or "",
		"tags": list(thread.tags or []),
		"is_archived": thread.is_archived,
		"project_ids": [str(p.id) for p in (thread.projects or [])],
		# acl fields - populated at vectorize time from access_rules table
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}


async def _thread_should_revectorize(
	thread: Thread,
	thread_in: ThreadUpdate,
	session: AsyncSession,
) -> bool:
	"""return whether an update touches fields represented in vectors."""
	# catalog summary changes are revectorized by thread maintenance.
	_fields = {"title", "tags", "metadata_", "owner_id"}
	update_data = thread_in.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


def thread_to_search_item(
	thread: Thread, score: float | None = None
) -> SearchResultItem:
	"""projection from a thread (and optional score) to a SearchResultItem."""
	summary = latest_active_summary_text(thread, SummaryPurpose.CATALOG)
	if summary is None:
		summary = (thread.metadata_ or {}).get("summary")
	return SearchResultItem(
		type=SearchResultType.THREAD,
		id=TypeID(thread.id),
		title=thread.title or "",
		preview=str(summary)[:100] if summary else None,
		score=score,
		created_at=thread.created_at,
		updated_at=thread.updated_at,
	)


THREAD_SPEC: VectorSpec[Thread] = VectorSpec(
	resource_type=VectorChunkResourceType.THREAD,
	resource_id=lambda t: str(t.id),
	dense_text=_thread_dense_text,
	bm25_text=_thread_bm25_text,
	metadata=_thread_metadata,
	should_revectorize=_thread_should_revectorize,
)


async def _vectorize_threads(threads: list[Thread], session: AsyncSession) -> int:
	"""embed and upsert the given threads (with acl metadata). returns count."""
	thread_ids = [str(t.id) for t in threads]
	if not thread_ids:
		return 0
	acl_by_id = await fetch_bulk_acl_metadata(thread_ids, ResourceType.THREAD, session)
	return await vectorize_resources(
		spec=THREAD_SPEC,
		resources=threads,
		session=session,
		extra_metadata_by_id=acl_by_id,
	)


async def vectorize_threads(thread_ids: Sequence[TypeID], session: AsyncSession) -> int:
	"""vectorize specific threads by id from their title.

	intended for freshly imported threads that have no catalog summary yet:
	the dense text is the title alone (the spec appends a summary only once
	one exists), so only threads with a non-empty title are vectorized.
	thread maintenance later generates a catalog summary and re-vectorizes
	with richer text. returns count.
	"""
	if not thread_ids:
		return 0
	stmt = (
		select(Thread)
		.where(
			Thread.id.in_([str(tid) for tid in thread_ids]),
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.summaries),
			selectinload(Thread.projects),
		)
	)
	result = await session.execute(stmt)
	threads = [th for th in result.scalars().unique().all() if (th.title or "").strip()]
	return await _vectorize_threads(threads, session)


async def vectorize_all_threads(session: AsyncSession) -> int:
	"""vectorize all non-deleted, non-temporary threads in bulk. returns count."""
	stmt = (
		select(Thread)
		.where(
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.summaries),
			selectinload(Thread.projects),
		)
	)
	result = await session.execute(stmt)
	return await _vectorize_threads(list(result.scalars().unique().all()), session)


def _thread_search_conditions(
	filters: ThreadSearchFilters | None,
) -> list[vectorstore_service.FieldCondition]:
	"""vector-layer narrowing conditions derived from thread search filters."""
	conditions: list[vectorstore_service.FieldCondition] = []
	if filters is None:
		return conditions
	if filters.owner_id is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="owner_id", value=str(filters.owner_id))
		)
	if filters.is_archived is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="is_archived", value=filters.is_archived)
		)
	return conditions


def _apply_thread_search_filters(
	stmt: Select,
	filters: ThreadSearchFilters | None,
) -> Select:
	"""SQL-layer narrowing mirroring _thread_search_conditions."""
	if filters is None:
		return stmt.where(Thread.is_temporary.is_(False))
	if not filters.include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))
	if filters.include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	if filters.owner_id is not None:
		stmt = stmt.where(Thread.owner_id == filters.owner_id)
	if filters.is_archived is not None:
		stmt = stmt.where(Thread.is_archived.is_(filters.is_archived))
	return stmt


async def _autocomplete_threads(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: ThreadSearchFilters | None = None,
) -> list[ScoredResult[Thread]]:
	"""pg_trgm autocomplete tier scored by title similarity."""
	pattern = contains_pattern(q)
	sim = func.similarity(Thread.title, q)
	stmt = (
		select(Thread, sim.label("sim"))
		.options(selectinload(Thread.messages), selectinload(Thread.summaries))
		.where(
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			),
			or_(
				sim > 0.1,
				Thread.title.ilike(pattern, escape="\\"),
			),
		)
		.order_by(sim.desc())
		.offset(offset)
		.limit(limit)
	)
	stmt = _apply_thread_search_filters(stmt, filters)
	result = await db.execute(stmt)
	return [ScoredResult(item=t, score=float(s)) for t, s in result.unique().all()]


async def _hybrid_search_threads(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: ThreadSearchFilters | None = None,
) -> list[ScoredResult[Thread]]:
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
	query_filter = vectorstore_service.with_conditions(
		vector_acl_filter([VectorChunkResourceType.THREAD], principal),
		_thread_search_conditions(filters),
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
	resource_ids = [r.metadata["resource_id"] for r in results]
	stmt = (
		select(Thread)
		.options(selectinload(Thread.messages), selectinload(Thread.summaries))
		.where(
			Thread.id.in_(resource_ids),
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			),
		)
	)
	stmt = _apply_thread_search_filters(stmt, filters)
	db_result = await db.execute(stmt)
	by_id = {str(t.id): t for t in db_result.scalars().unique().all()}
	scored: list[ScoredResult[Thread]] = []
	for r in results:
		thread = by_id.get(str(r.metadata["resource_id"]))
		if thread is None:
			continue
		scored.append(ScoredResult(item=thread, score=r.score))
	return scored


async def search_threads(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	offset: int = 0,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: ThreadSearchFilters | None = None,
	score_threshold: float = 0.0,
) -> list[ScoredResult[Thread]]:
	"""relevance-ordered, deduped thread hits with internal scores.

	hybrid tier ranks first; autocomplete-only matches are appended.
	"""
	params = search_params or SearchParams()
	if filters and (filters.include_deleted or filters.include_hidden):
		if not principal.is_admin:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		if params.mode != SearchMode.AUTOCOMPLETE:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="include_deleted/include_hidden requires autocomplete mode",
			)
	if params.mode == SearchMode.AUTOCOMPLETE:
		return await _autocomplete_threads(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
	fetch = offset + limit
	coros: list[Coroutine[None, None, list[ScoredResult[Thread]]]] = []
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

	async def _run_hybrid() -> list[ScoredResult[Thread]]:
		async with session_scope(None) as s:
			return await _hybrid_search_threads(
				query_text,
				s,
				principal=principal,
				limit=fetch,
				search_params=params,
				query_embedding=query_embedding,
				filters=filters,
			)

	async def _run_autocomplete() -> list[ScoredResult[Thread]]:
		async with session_scope(None) as s:
			return await _autocomplete_threads(
				query_text, s, principal=principal, limit=fetch, filters=filters
			)

	if run_hybrid:
		coros.append(_run_hybrid())
	if run_autocomplete:
		coros.append(_run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="threads")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]
