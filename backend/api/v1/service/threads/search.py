"""service helpers for threads and messages."""

import asyncio
import logging
from collections.abc import Coroutine

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.database.main import session_scope
from api.models.access_rule import AccessLevel
from api.models.message import Message
from api.models.project import Project
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose
from api.permissions import ResourceType
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResourceReferenceType,
	SearchResultAnchor,
	SearchResultItem,
	SearchResultType,
)
from api.schemas.thread import (
	ParticipantStatus,
	ThreadSearchFilters,
	ThreadUpdate,
	participant_state_filters,
)
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	fetch_bulk_acl_metadata,
	resource_access_predicate,
	vector_acl_filter,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.search.grouping import ResourceHitGroup, group_resource_hits
from api.v1.service.search.primitives import ScoredResult, SearchHit, merge_scored
from api.v1.service.threads.common import (
	apply_participant_scope,
	multi_writer_thread_ids,
)
from api.v1.service.threads.content_vectors import (
	ANCHOR_MESSAGE_ID_KEY,
	ENRICHMENT_KEY,
	THREAD_CONTENT_RESOURCE_TYPE,
)
from api.v1.service.threads.summaries import latest_active_summary_text
from api.v1.service.threads.tree import active_branch_message_ids, visible_message_ids
from api.v1.service.threads.user_state import (
	STATE_VECTOR_FIELDS,
	apply_participant_state_filters,
	thread_state_vector_metadata,
)
from api.v1.service.vectorize import (
	VectorSpec,
	filter_unvectorized,
	vectorize_resources,
)
from api.v1.service.vectorstores import (
	FieldCondition,
	FieldMatch,
	VectorChunkResourceType,
	merge_filters,
	search,
)
from nokodo_ai.adapters.base.vectorstores import ChunkFilter, ChunkSearchResult
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_VECTOR_OVERFETCH_FACTOR = 4
_MESSAGE_AUTOCOMPLETE_OVERFETCH_FACTOR = 3
_MAX_MATCHED_CHUNKS = 3
_MATCHED_CHUNK_PREVIEW_CHARS = 500
_SNIPPET_CHARS = 240
"""width of the autocomplete match window."""

_PASSAGE_PREVIEW_CHARS = 300
"""width of the passage transcript preview."""


def _message_anchor(message_id: str) -> SearchResultAnchor:
	"""anchor focusing the message that produced a thread hit."""
	return SearchResultAnchor(
		type=SearchResourceReferenceType.MESSAGE,
		id=TypeID(message_id),
	)


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
	"""build sparse search text from dense fields plus tags.

	message content is indexed separately as transcript passages
	(thread_content chunks), not folded into the thread point.
	"""
	dense = _thread_dense_text(thread)
	parts = [dense] if dense else []
	tags = " ".join(tag for tag in (thread.tags or []) if tag)
	if tags:
		parts.append(tags)
	return " ".join(parts).strip()


def _thread_metadata(thread: Thread) -> JSONObject:
	"""build vector metadata for a thread resource."""
	return {
		"resource_type": VectorChunkResourceType.THREAD.value,
		"owner_id": str(thread.owner_id),
		"title": thread.title or "",
		"tags": list(thread.tags or []),
		"project_ids": [str(p.id) for p in (thread.projects or [])],
		# acl fields - populated at vectorize time from access_rules table
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
		# per-user state - populated at vectorize time from participant rows
		**{field: [] for field in STATE_VECTOR_FIELDS},
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
		id=thread.id,
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
	"""embed and upsert the given threads (with acl + state metadata)."""
	thread_ids = [str(t.id) for t in threads]
	if not thread_ids:
		return 0
	acl_by_id = await fetch_bulk_acl_metadata(thread_ids, ResourceType.THREAD, session)
	state_by_id = await thread_state_vector_metadata(session, thread_ids)
	extra_by_id = {
		thread_id: {**acl_by_id.get(thread_id, {}), **state_by_id.get(thread_id, {})}
		for thread_id in thread_ids
	}
	return await vectorize_resources(
		spec=THREAD_SPEC,
		resources=threads,
		session=session,
		extra_metadata_by_id=extra_by_id,
	)


async def vectorize_threads(
	session: AsyncSession,
	ids: list[TypeID] | None = None,
) -> int:
	"""vectorize thread points; ids=None means every non-deleted, non-temporary
	thread. threads with an empty title are skipped when targeting ids (fresh
	imports without a catalog summary have no dense text yet). returns count.
	"""
	if ids is not None and not ids:
		return 0
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
	if ids is not None:
		stmt = stmt.where(Thread.id.in_([str(tid) for tid in ids]))
	result = await session.execute(stmt)
	threads = list(result.scalars().unique().all())
	if ids is not None:
		threads = [th for th in threads if (th.title or "").strip()]
	return await _vectorize_threads(threads, session)


async def vectorize_stale_threads(
	thread_ids: list[TypeID],
	session: AsyncSession,
) -> int:
	"""re-vectorize the thread points whose stored vectors are stale. returns count."""
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
	pending = await filter_unvectorized(THREAD_SPEC, threads, session)
	return await _vectorize_threads(pending, session)


_STATE_VECTOR_KEYS: dict[ParticipantStatus, str] = {
	"archived": "archived_by",
	"muted": "muted_by",
	"pinned": "pinned_by",
	"invite_pending": "invite_pending_to",
}


def _thread_search_filter(filters: ThreadSearchFilters | None) -> ChunkFilter:
	"""translate thread search filters into vector-layer conditions.

	EVERY filter must be expressible here: the SQL pass that follows is a
	redundant second layer, never the gate, so anything only enforceable in
	SQL would silently truncate a page instead of narrowing it.
	"""
	if filters is None:
		return ChunkFilter()
	required: list[FieldCondition] = []
	excluded: list[FieldCondition] = []
	if filters.owner_id is not None:
		required.append(FieldMatch(key="owner_id", value=str(filters.owner_id)))
	if filters.project_id is not None:
		required.append(FieldMatch(key="project_ids", value=str(filters.project_id)))
	for state, include_id, exclude_id in participant_state_filters(filters):
		key = _STATE_VECTOR_KEYS[state]
		if include_id is not None:
			required.append(FieldMatch(key=key, value=str(include_id)))
		if exclude_id is not None:
			excluded.append(FieldMatch(key=key, value=str(exclude_id)))
	return ChunkFilter(all_of=required, none_of=excluded)


def _apply_thread_search_filters(
	stmt: Select,
	filters: ThreadSearchFilters | None,
	principal: Principal,
) -> Select:
	"""SQL mirror of ``_thread_search_filter``.

	for the vector tier this is a redundant second layer (the vector filter is
	the gate); for the pg_trgm autocomplete tier, which never touches the
	vectorstore, it is the only layer - so both must stay in step.
	"""
	if filters is None:
		return stmt.where(Thread.is_temporary.is_(False))
	if not filters.include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))
	if filters.include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	if filters.owner_id is not None:
		stmt = stmt.where(Thread.owner_id == filters.owner_id)
	if filters.project_id is not None:
		stmt = stmt.where(Thread.projects.any(Project.id == str(filters.project_id)))
	stmt = apply_participant_scope(stmt, filters.participant_scope)
	return apply_participant_state_filters(stmt, filters, principal)


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
	stmt = _apply_thread_search_filters(stmt, filters, principal)
	result = await db.execute(stmt)
	return [ScoredResult(item=t, score=float(s)) for t, s in result.unique().all()]


async def _autocomplete_messages(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: ThreadSearchFilters | None = None,
) -> list[ScoredResult[Thread]]:
	"""pg_trgm autocomplete tier over message text, one hit per thread.

	word_similarity scores the best-matching extent inside long messages.
	hits off the active branch are filtered out; results carry the matched
	message id as a jump-to anchor.
	"""
	pattern = contains_pattern(q)
	sim = func.word_similarity(q, Message.search_text)
	fetch = max(limit, limit * _MESSAGE_AUTOCOMPLETE_OVERFETCH_FACTOR)
	stmt = (
		select(Message.id, Message.thread_id, Message.search_text, sim.label("sim"))
		.join(Thread, Thread.id == Message.thread_id)
		.where(
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			),
			Message.search_text.is_not(None),
			or_(
				sim > 0.1,
				Message.search_text.ilike(pattern, escape="\\"),
			),
		)
		.order_by(sim.desc())
		.offset(offset)
		.limit(fetch)
	)
	stmt = _apply_thread_search_filters(stmt, filters, principal)
	rows = (await db.execute(stmt)).all()
	if not rows:
		return []
	include_all = bool(filters and filters.include_all_branches)
	thread_ids = list(dict.fromkeys(str(thread_id) for _, thread_id, _, _ in rows))
	active: dict[str, set[str]] = {}
	shared_visible: dict[str, set[str]] = {}
	if include_all:
		shared_visible = await _shared_thread_visible_ids(db, thread_ids)
	else:
		active = await active_branch_message_ids(db, thread_ids)
	best: dict[str, tuple[str, float, str]] = {}
	for message_id, thread_id, text, score in rows:
		tid = str(thread_id)
		mid = str(message_id)
		if not _hit_is_visible(tid, mid, include_all, active, shared_visible):
			continue
		if tid not in best:
			# window around the match, biased to keep some leading context
			content = text or ""
			match_at = content.lower().find(q.lower())
			start = max(match_at - _SNIPPET_CHARS // 3, 0) if match_at >= 0 else 0
			best[tid] = (mid, float(score), content[start : start + _SNIPPET_CHARS])
	if not best:
		return []
	stmt = (
		select(Thread)
		.options(selectinload(Thread.messages), selectinload(Thread.summaries))
		.where(Thread.id.in_(list(best.keys())))
	)
	stmt = _apply_thread_search_filters(stmt, filters, principal)
	by_id = {str(t.id): t for t in (await db.execute(stmt)).scalars().unique().all()}
	scored: list[ScoredResult[Thread]] = []
	for tid, (mid, score, snippet) in best.items():
		thread = by_id.get(tid)
		if thread is None:
			continue
		hit = SearchHit(anchor=_message_anchor(mid), preview=snippet)
		scored.append(ScoredResult(item=thread, score=score, hit=hit))
		if len(scored) >= limit:
			break
	return scored


def _thread_id_for_hit(hit: ChunkSearchResult) -> str | None:
	"""resolve the thread id represented by a thread or thread_content hit."""
	if hit.metadata.get("resource_type") == THREAD_CONTENT_RESOURCE_TYPE.value:
		parent_id = hit.metadata.get("parent_resource_id")
		return parent_id if isinstance(parent_id, str) else None
	resource_id = hit.metadata.get("resource_id")
	return resource_id if isinstance(resource_id, str) else None


def _hit_anchor_message_id(hit: ChunkSearchResult) -> str | None:
	anchor = hit.metadata.get(ANCHOR_MESSAGE_ID_KEY)
	return anchor if isinstance(anchor, str) else None


async def _shared_thread_visible_ids(
	db: AsyncSession,
	thread_ids: list[str],
) -> dict[str, set[str]]:
	"""readable message ids per multi-writer thread, for the all-branches path.

	``include_all_branches`` reaches abandoned branches, which in a shared
	thread were never part of the conversation. solo threads are absent from
	the map and stay unrestricted.
	"""
	shared = await multi_writer_thread_ids(db, thread_ids)
	if not shared:
		return {}
	return await visible_message_ids(db, sorted(shared))


def _hit_is_visible(
	thread_id: str,
	message_id: str,
	include_all: bool,
	active: dict[str, set[str]],
	shared_visible: dict[str, set[str]],
) -> bool:
	"""whether a message hit may surface for the current branch filter."""
	if not include_all:
		return message_id in active.get(thread_id, set())
	readable = shared_visible.get(thread_id)
	return readable is None or message_id in readable


def _valid_group_hits(
	group: ResourceHitGroup,
	readable_ids: set[str],
) -> list[ChunkSearchResult]:
	"""keep thread-point hits plus passage hits anchored on a readable message."""
	valid: list[ChunkSearchResult] = []
	for hit in group.hits:
		anchor = _hit_anchor_message_id(hit)
		if anchor is None or anchor in readable_ids:
			valid.append(hit)
	return valid


async def _hybrid_search_threads(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: ThreadSearchFilters | None = None,
) -> list[ScoredResult[Thread]]:
	"""qdrant hybrid tier (dense + BM25) over thread points and passages.

	thread metadata points and transcript passage chunks are searched in one
	query, folded to one result per thread, filtered to the active branch,
	and anchored to the best matching message.
	"""
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
	searched_types = [VectorChunkResourceType.THREAD]
	if settings.assets.thread_passages.enabled:
		searched_types.append(THREAD_CONTENT_RESOURCE_TYPE)
	query_filter = merge_filters(
		vector_acl_filter(searched_types, principal),
		_thread_search_filter(filters),
	)
	vector_limit = max(limit, limit * _VECTOR_OVERFETCH_FACTOR)
	results = await search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=vector_limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	groups = group_resource_hits(results, _thread_id_for_hit)
	include_all = bool(filters and filters.include_all_branches)
	passage_thread_ids = [
		tid
		for tid, group in groups.items()
		if any(_hit_anchor_message_id(hit) is not None for hit in group.hits)
	]
	active: dict[str, set[str]] = {}
	shared_visible: dict[str, set[str]] = {}
	if include_all:
		shared_visible = await _shared_thread_visible_ids(db, passage_thread_ids)
	else:
		active = await active_branch_message_ids(db, passage_thread_ids)
	stmt = (
		select(Thread)
		.options(selectinload(Thread.messages), selectinload(Thread.summaries))
		.where(
			Thread.id.in_(list(groups.keys())),
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			),
		)
	)
	stmt = _apply_thread_search_filters(stmt, filters, principal)
	db_result = await db.execute(stmt)
	by_id = {str(t.id): t for t in db_result.scalars().unique().all()}
	scored: list[ScoredResult[Thread]] = []
	for tid, group in groups.items():
		thread = by_id.get(tid)
		if thread is None:
			continue
		if include_all:
			readable = shared_visible.get(tid)
			valid = (
				list(group.hits)
				if readable is None
				else _valid_group_hits(group, readable)
			)
		else:
			valid = _valid_group_hits(group, active.get(tid, set()))
		if not valid:
			continue
		best = max(valid, key=lambda hit: hit.score)
		anchor_hit = best if _hit_anchor_message_id(best) is not None else None
		if anchor_hit is None:
			passage_hits = [
				hit for hit in valid if _hit_anchor_message_id(hit) is not None
			]
			if passage_hits:
				anchor_hit = max(passage_hits, key=lambda hit: hit.score)
		valid_group = ResourceHitGroup(resource_id=tid, hits=valid)
		matched_chunks = valid_group.matched_chunks(
			_MAX_MATCHED_CHUNKS, _MATCHED_CHUNK_PREVIEW_CHARS
		)
		anchor = _hit_anchor_message_id(anchor_hit) if anchor_hit is not None else None
		preview: str | None = None
		if anchor_hit is not None and anchor is not None:
			# preview the transcript, not the enrichment blurb prefixed onto it
			transcript = anchor_hit.content
			blurb = anchor_hit.metadata.get(ENRICHMENT_KEY)
			if isinstance(blurb, str) and blurb and transcript.startswith(blurb):
				transcript = transcript[len(blurb) :].lstrip()
			preview = transcript[:_PASSAGE_PREVIEW_CHARS]
		hit = SearchHit(
			anchor=_message_anchor(anchor) if anchor is not None else None,
			preview=preview,
			matched_chunks=matched_chunks,
		)
		scored.append(ScoredResult(item=thread, score=best.score, hit=hit))
		if len(scored) >= limit:
			break
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
		if not principal.user.is_superuser:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		if params.mode != SearchMode.AUTOCOMPLETE:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="include_deleted/include_hidden requires autocomplete mode",
			)
	if params.mode == SearchMode.AUTOCOMPLETE:
		# sequential on purpose: both tiers share the caller's session and
		# AsyncSession forbids concurrent operations.
		title_hits = await _autocomplete_threads(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
		message_hits = await _autocomplete_messages(
			query_text,
			db,
			principal=principal,
			limit=limit,
			offset=offset,
			filters=filters,
		)
		return merge_scored([title_hits, message_hits], resource_name="threads")[:limit]
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

	async def _run_autocomplete_messages() -> list[ScoredResult[Thread]]:
		async with session_scope(None) as s:
			return await _autocomplete_messages(
				query_text, s, principal=principal, limit=fetch, filters=filters
			)

	if run_hybrid:
		coros.append(_run_hybrid())
	if run_autocomplete:
		coros.append(_run_autocomplete())
		coros.append(_run_autocomplete_messages())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="threads")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]
