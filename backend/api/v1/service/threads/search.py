"""service helpers for threads and messages."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import (
	build_cursor_page,
	decode_cursor,
)
from api.models.access_rule import AccessLevel
from api.models.message import MessageType
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.schemas.thread import ThreadUpdate
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	fetch_bulk_acl_metadata,
	thread_access_predicate,
	vector_acl_filter,
)
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	remove_vectorized_resource,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _thread_dense_text(thread: Thread) -> str:
	parts: list[str] = []
	if thread.title:
		parts.append(thread.title)
	summary = (thread.metadata_ or {}).get("summary")
	if summary:
		parts.append(str(summary))
	return " ".join(parts).strip()


def _thread_bm25_text(thread: Thread) -> str:
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
	return {
		"resource_type": "thread",
		"owner_id": str(thread.owner_id),
		"title": thread.title or "",
		"tags": list(thread.tags or []),
		"is_archived": thread.is_archived,
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
	# title/tags are metadata-only; summary change is detected via metadata_ key
	_fields = {"title", "tags", "metadata_", "owner_id"}
	update_data = thread_in.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


THREAD_SPEC: VectorSpec[Thread] = VectorSpec(
	resource_type="thread",
	resource_id=lambda t: str(t.id),
	dense_text=_thread_dense_text,
	bm25_text=_thread_bm25_text,
	metadata=_thread_metadata,
	should_revectorize=_thread_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_all_threads(session: AsyncSession) -> int:
	"""vectorize all non-deleted, non-temporary threads in bulk. returns count."""
	stmt = (
		select(Thread)
		.where(
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		.options(selectinload(Thread.messages))
	)
	result = await session.execute(stmt)
	valid: list[tuple[Thread, str]] = []
	for th in result.scalars().unique().all():
		text = _thread_dense_text(th)
		if text.strip():
			valid.append((th, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	thread_ids = [str(t.id) for t, _ in valid]
	acl_by_id = await fetch_bulk_acl_metadata(thread_ids, ResourceType.THREAD, session)
	chunks = []
	for (thread, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=THREAD_SPEC, resource_id=str(thread.id), session=session
		)
		acl = acl_by_id.get(str(thread.id))
		chunks.append(build_chunk(THREAD_SPEC, thread, emb, extra_metadata=acl))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_threads(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for threads on title."""
	pattern = contains_pattern(q)
	stmt = (
		select(Thread)
		.where(
			Thread.is_temporary.is_(False),
			thread_access_predicate(
				principal,
				required_level=AccessLevel.READER,
				include_hidden=False,
			),
			or_(
				func.similarity(Thread.title, q) > 0.1,
				Thread.title.ilike(pattern, escape="\\"),
			),
		)
		.order_by(func.similarity(Thread.title, q).desc())
		.limit(limit)
	)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.THREAD,
			id=TypeID(t.id),
			title=t.title or "",
			preview=None,
			created_at=t.created_at,
			updated_at=t.updated_at,
		)
		for t in result.scalars().unique().all()
	]


async def _hybrid_search_threads(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for threads (dense + BM25)."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (await embed_text(text=query_text, session=db) if need_dense else None)
	)
	text_query = query_text if need_sparse else None
	query_filter = vector_acl_filter(ResourceType.THREAD, principal)
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
	resource_ids = [r.metadata["resource_id"] for r in results]
	stmt = select(Thread).where(
		Thread.id.in_(resource_ids),
		Thread.deleted_at.is_(None),
		Thread.is_temporary.is_(False),
		thread_access_predicate(
			principal,
			required_level=AccessLevel.READER,
			include_hidden=False,
		),
	)
	db_result = await db.execute(stmt)
	by_id = {str(t.id): t for t in db_result.scalars().unique().all()}
	score_by_rid = {str(r.metadata["resource_id"]): r.score for r in results}
	items: list[SearchResultItem] = []
	for r in results:
		rid = str(r.metadata["resource_id"])
		thread = by_id.get(rid)
		if not thread:
			continue
		summary = (thread.metadata_ or {}).get("summary")
		items.append(
			SearchResultItem(
				type=SearchResultType.THREAD,
				id=TypeID(thread.id),
				title=thread.title or "",
				preview=(str(summary)[:100] if summary else None),
				score=score_by_rid.get(rid),
				created_at=thread.created_at,
				updated_at=thread.updated_at,
			)
		)
	return items


async def search_threads(
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
	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(
			_hybrid_search_threads(
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
			_autocomplete_threads(query_text, db, principal=principal, limit=limit + 1)
		)
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results, limit + 1, resource_name="threads"
	)
	if cursor:
		ts, cid = decode_cursor(cursor)
		_sk = THREAD_SPEC.sort_key
		items = [i for i in items if (getattr(i, _sk), str(i.id)) < (ts, cid)]
	_sk = THREAD_SPEC.sort_key
	items.sort(key=lambda r: (getattr(r, _sk), str(r.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=THREAD_SPEC.sort_key)
