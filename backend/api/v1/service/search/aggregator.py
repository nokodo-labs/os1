"""cross-resource search aggregator.

imports search functions FROM individual resource services and
orchestrates global (cross-resource) search operations.

for resource-specific search (notes, threads, reminders, memories),
the logic lives in each resource's service module.
"""

import asyncio
import logging
from collections.abc import (
	AsyncIterator,
	Awaitable,
	Callable,
	Collection,
	Coroutine,
)
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.file import File
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.settings import settings
from api.v1.service.authentication import Principal, load_principal_for_user
from api.v1.service.authorization import (
	ACL_REVISION_KEY,
	ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES,
	VECTOR_CHUNK_ACCESS_RESOURCE_TYPES,
	VECTOR_CHUNK_PARENT_RESOURCE_TYPES,
	fetch_bulk_acl_revisions,
)
from api.v1.service.calendar import (
	calendar_or_event_to_search_item,
	search_calendars,
	vectorize_calendar_events,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.files import (
	file_to_search_item,
	search_files,
	vectorize_file_descriptions,
	vectorize_files,
)
from api.v1.service.files.processing import (
	CONTENT_PIPELINE_SOURCES,
	start_file_processing_task,
)
from api.v1.service.files.text_contents import (
	file_content_config_fp,
	file_content_stale_predicate,
)
from api.v1.service.memories import vectorize_memories
from api.v1.service.notes import (
	note_to_search_item,
	search_notes,
	vectorize_notes,
)
from api.v1.service.projects import project_to_search_item, search_projects
from api.v1.service.reminders import (
	reminder_or_list_to_search_item,
	search_reminder_lists,
	vectorize_reminders,
)
from api.v1.service.search.primitives import (
	ScoredResult,
	apply_hit,
	relevance_sort_key,
)
from api.v1.service.threads import (
	search_threads,
	thread_to_search_item,
	vectorize_threads,
)
from api.v1.service.threads.content_vectors import (
	content_vectors_stale_predicate,
)
from api.v1.service.threads.vectorization import schedule_thread_content_vectorization
from api.v1.service.vectorize import (
	CONFIG_FP_KEY,
	PIPELINE_VERSION_KEY,
	StaleBy,
	chunk_stamps_stale,
	sync_resource_refs_vector_acl,
)
from api.v1.service.vectorstores import (
	VectorChunkResourceType,
	resource_types_filter,
	scroll_chunks,
)
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.types.json import JSONArray, JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


class AnchorFanout(StrEnum):
	"""how many results one container yields when several of its sub-resources match."""

	BEST = "best"
	"""one result per container; the best-scored match provides the anchor."""

	ALL = "all"
	"""every matched sub-resource is its own result (same id, distinct anchors)."""


ANCHOR_FANOUT: dict[SearchResultType, AnchorFanout] = {
	SearchResultType.THREAD: AnchorFanout.BEST,
	SearchResultType.NOTE: AnchorFanout.BEST,
	SearchResultType.REMINDER_LIST: AnchorFanout.ALL,
	SearchResultType.CALENDAR: AnchorFanout.ALL,
	SearchResultType.PROJECT: AnchorFanout.BEST,
	SearchResultType.FILE: AnchorFanout.BEST,
	SearchResultType.MEMORY: AnchorFanout.BEST,
}
"""per-container anchor fanout for search results."""


def _dedupe_key(item: SearchResultItem) -> str:
	"""result identity for aggregator dedupe, honoring the container's anchor fanout."""
	fanout = ANCHOR_FANOUT.get(item.type, AnchorFanout.BEST)
	if fanout is AnchorFanout.ALL and item.anchor is not None:
		return f"{item.id}#{item.anchor.id}"
	return str(item.id)


async def _collect[T: Any](
	coro: Coroutine[None, None, list[ScoredResult[T]]],
	projector: Callable[[T, float | None], SearchResultItem],
	limit: int,
) -> list[SearchResultItem]:
	"""await a scored coro and map results to SearchResultItem."""
	return [
		apply_hit(projector(scored.item, scored.score), scored.hit)
		for scored in (await coro)[:limit]
	]


async def search_stream(
	q: str,
	db: AsyncSession,
	principal: Principal,
	types: list[SearchResultType] | None = None,
	limit: int = 10,
	search_params: SearchParams | None = None,
) -> AsyncIterator[SearchResultItem]:
	"""stream search results as they complete from each resource type.

	memories are excluded from global search.
	"""
	if types is None:
		types = [
			SearchResultType.NOTE,
			SearchResultType.THREAD,
			SearchResultType.REMINDER_LIST,
			SearchResultType.CALENDAR,
			SearchResultType.PROJECT,
			SearchResultType.FILE,
		]

	# embed query once instead of per-resource-type to avoid redundant API calls
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	dense_types = {
		SearchResultType.NOTE,
		SearchResultType.THREAD,
		SearchResultType.REMINDER_LIST,
		SearchResultType.CALENDAR,
		SearchResultType.FILE,
	}
	query_embedding = (
		await embed_text(text=q, session=db, input_type="query")
		if need_dense and any(result_type in dense_types for result_type in types)
		else None
	)

	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	if SearchResultType.NOTE in types:
		coros.append(
			_collect(
				search_notes(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				note_to_search_item,
				limit,
			)
		)
	if SearchResultType.THREAD in types:
		coros.append(
			_collect(
				search_threads(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				thread_to_search_item,
				limit,
			)
		)
	if SearchResultType.REMINDER_LIST in types:
		coros.append(
			_collect(
				search_reminder_lists(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				reminder_or_list_to_search_item,
				limit,
			)
		)
	if SearchResultType.CALENDAR in types:
		coros.append(
			_collect(
				search_calendars(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				calendar_or_event_to_search_item,
				limit,
			)
		)
	if SearchResultType.PROJECT in types:
		coros.append(
			_collect(
				search_projects(
					q,
					db,
					principal=principal,
					limit=limit,
				),
				project_to_search_item,
				limit,
			)
		)
	if SearchResultType.FILE in types:
		coros.append(
			_collect(
				search_files(
					q,
					db,
					principal=principal,
					limit=limit,
					search_params=search_params,
					query_embedding=query_embedding,
				),
				file_to_search_item,
				limit,
			)
		)

	tier_results = await asyncio.gather(*coros, return_exceptions=True)
	all_items: list[SearchResultItem] = []
	for tier in tier_results:
		if isinstance(tier, BaseException):
			logger.warning("search tier failed", exc_info=tier)
			continue
		all_items.extend(tier)

	# best-scored first (unscored last) so same-container dedupe keeps the top
	# match regardless of which tier produced it
	all_items.sort(key=relevance_sort_key)
	seen: set[str] = set()
	deduped: list[SearchResultItem] = []
	for item in all_items:
		key = _dedupe_key(item)
		if key not in seen:
			seen.add(key)
			deduped.append(item)

	# TODO: reranking hook — when a reranker is available in the SDK, call it
	# here on `deduped[:limit]` before yielding. reranking normalises scores
	# across resource types and makes cross-type ordering meaningful.

	for item in deduped[:limit]:
		yield item


async def vectorize(
	db: AsyncSession,
	by: Collection[StaleBy] | None = None,
) -> JSONObject:
	"""rebuild vectors across every pipeline; `by` narrows to stale resources.

	without `by`: rebuilds every resource's point inline (file content
	converges within the file pass) and dispatches a passage reconcile for
	every thread. with `by` (causes OR-combined): rebuilds only resources
	provenance-stale by those causes - stale points inline, stale thread
	passages and file contents via their rebuild tasks. `resources` counts
	are keyed by chunk type in both shapes.
	"""
	if by is not None:
		return await _vectorize_stale(_causes(by), db)
	file_count = await vectorize_files(db)
	resources: JSONObject = {
		VectorChunkResourceType.NOTE.value: await vectorize_notes(db),
		VectorChunkResourceType.THREAD.value: (await vectorize_threads(db)),
		VectorChunkResourceType.REMINDER.value: (await vectorize_reminders(db)),
		VectorChunkResourceType.CALENDAR_EVENT.value: (
			await vectorize_calendar_events(db)
		),
		VectorChunkResourceType.FILE.value: file_count,
		VectorChunkResourceType.MEMORY.value: (await vectorize_memories(db)),
	}
	thread_ids: list[str] = []
	if settings.assets.thread_passages.enabled:
		thread_stmt = select(Thread.id).where(
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		thread_ids = [str(row[0]) for row in (await db.execute(thread_stmt)).all()]
		for thread_id in thread_ids:
			await schedule_thread_content_vectorization(TypeID(thread_id))
	return {
		"by": None,
		"resources": resources,
		"thread_content": len(thread_ids),
		"file_content": file_count,
	}


_GENERIC_REBUILDERS: dict[
	VectorChunkResourceType,
	Callable[[AsyncSession, list[TypeID]], Awaitable[int]],
] = {
	VectorChunkResourceType.NOTE: vectorize_notes,
	VectorChunkResourceType.MEMORY: vectorize_memories,
	VectorChunkResourceType.THREAD: vectorize_threads,
	VectorChunkResourceType.REMINDER: vectorize_reminders,
	VectorChunkResourceType.CALENDAR_EVENT: vectorize_calendar_events,
	VectorChunkResourceType.FILE: vectorize_file_descriptions,
}
"""per chunk type, the unconditional vectorizer for the generic pipeline."""

_GENERIC_CHUNK_TYPES = tuple(_GENERIC_REBUILDERS)
"""chunk types written by the generic single-tier pipeline."""


def _causes(by: Collection[StaleBy]) -> set[StaleBy]:
	causes = set(by)
	if not causes:
		raise ValueError("at least one staleness cause is required")
	return causes


async def _stale_thread_ids(causes: set[StaleBy], db: AsyncSession) -> list[str]:
	"""ids of threads whose passage vectors are provenance-stale by any cause."""
	if not causes or not settings.assets.thread_passages.enabled:
		return []
	stmt = select(Thread.id).where(
		Thread.deleted_at.is_(None),
		Thread.is_temporary.is_(False),
		or_(*(content_vectors_stale_predicate(cause) for cause in causes)),
	)
	return [str(row[0]) for row in (await db.execute(stmt)).all()]


async def _stale_files(causes: set[StaleBy], db: AsyncSession) -> list[File]:
	"""files whose content vectors are provenance-stale by any cause."""
	if not causes:
		return []
	config_fp = await file_content_config_fp(db) if StaleBy.CONFIG in causes else None
	stmt = select(File).where(
		File.deleted_at.is_(None),
		File.source.in_(CONTENT_PIPELINE_SOURCES),
		or_(
			*(
				file_content_stale_predicate(
					cause,
					config_fp=config_fp,
				)
				for cause in causes
			)
		),
	)
	return list((await db.execute(stmt)).scalars().all())


async def count_stale_vectors(
	by: Collection[StaleBy],
	db: AsyncSession,
) -> JSONObject:
	"""count resources whose vectors are provenance-stale by any given cause.

	causes combine as OR. read-only: the preview for vectorize(by=...).
	"""
	causes = _causes(by)
	by_values: JSONArray = [cause.value for cause in sorted(causes)]
	provenance_causes = causes - {StaleBy.ACL}
	provenance_ids_by_type = (
		await _stale_generic_resource_ids(provenance_causes, db)
		if provenance_causes
		else {chunk_type: [] for chunk_type in _GENERIC_CHUNK_TYPES}
	)
	stale_ids = {
		chunk_type: list(ids) for chunk_type, ids in provenance_ids_by_type.items()
	}
	if StaleBy.ACL in causes:
		_merge_acl_refs_into_stale_ids(
			stale_ids,
			await _stale_acl_resource_refs(db),
		)
	resources: JSONObject = {
		resource_type.value: len(ids) for resource_type, ids in stale_ids.items()
	}
	return {
		"by": by_values,
		"resources": resources,
		"thread_content": len(await _stale_thread_ids(provenance_causes, db)),
		"file_content": len(await _stale_files(provenance_causes, db)),
	}


async def _vectorize_stale(
	causes: set[StaleBy],
	db: AsyncSession,
) -> JSONObject:
	"""rebuild resources whose vectors are provenance-stale by any given cause.

	stale generic points rebuild inline through their by-ids rebuilders; stale
	thread passages and file contents dispatch their rebuild tasks.
	"""
	provenance_causes = causes - {StaleBy.ACL}
	provenance_ids_by_type = (
		await _stale_generic_resource_ids(provenance_causes, db)
		if provenance_causes
		else {chunk_type: [] for chunk_type in _GENERIC_CHUNK_TYPES}
	)
	stale_ids = {
		chunk_type: list(ids) for chunk_type, ids in provenance_ids_by_type.items()
	}
	stale_acl_refs = await _stale_acl_resource_refs(db) if StaleBy.ACL in causes else []
	_merge_acl_refs_into_stale_ids(stale_ids, stale_acl_refs)
	resources: JSONObject = {}
	for resource_type, ids in stale_ids.items():
		provenance_ids = provenance_ids_by_type[resource_type]
		if provenance_ids:
			await _GENERIC_REBUILDERS[resource_type](db, provenance_ids)
		resources[resource_type.value] = len(ids)
	if stale_acl_refs:
		await sync_resource_refs_vector_acl(stale_acl_refs, db)

	thread_ids = await _stale_thread_ids(provenance_causes, db)
	for thread_id in thread_ids:
		await schedule_thread_content_vectorization(TypeID(thread_id))

	stale_files = await _stale_files(provenance_causes, db)
	principals: dict[str, Principal] = {}
	for file in stale_files:
		owner_key = str(file.owner_id)
		principal = principals.get(owner_key)
		if principal is None:
			principal = await load_principal_for_user(TypeID(file.owner_id), db)
			principals[owner_key] = principal
		await start_file_processing_task(
			db,
			principal,
			file.id,
			force=True,
		)

	by_values: JSONArray = [cause.value for cause in sorted(causes)]
	return {
		"by": by_values,
		"resources": resources,
		"thread_content": len(thread_ids),
		"file_content": len(stale_files),
	}


_STALE_SCAN_PAYLOAD_FIELDS = [
	"resource_type",
	"resource_id",
	PIPELINE_VERSION_KEY,
	CONFIG_FP_KEY,
	ACL_REVISION_KEY,
	"parent_resource_type",
	"parent_resource_id",
]
"""the only payload keys the stale scan reads.

projecting to these keeps a full-corpus enumeration from materializing every
chunk's BM25 text. keep in sync with `chunk_stamps_stale`.
"""


async def _stale_generic_resource_ids(
	causes: set[StaleBy],
	db: AsyncSession,
) -> dict[VectorChunkResourceType, list[TypeID]]:
	"""ids of provenance-stale generic resources, grouped by chunk type."""
	chunks = await scroll_chunks(
		resource_types_filter(list(_GENERIC_CHUNK_TYPES)),
		db,
		payload_fields=_STALE_SCAN_PAYLOAD_FIELDS,
	)
	grouped: dict[tuple[str, str], list[Chunk]] = {}
	for chunk in chunks:
		resource_type = chunk.metadata.get("resource_type")
		resource_id = chunk.metadata.get("resource_id")
		if isinstance(resource_type, str) and isinstance(resource_id, str):
			grouped.setdefault((resource_type, resource_id), []).append(chunk)
	stale: dict[VectorChunkResourceType, list[TypeID]] = {
		chunk_type: [] for chunk_type in _GENERIC_CHUNK_TYPES
	}
	for (resource_type, resource_id), resource_chunks in grouped.items():
		if chunk_stamps_stale(resource_chunks, causes):
			stale.setdefault(VectorChunkResourceType(resource_type), []).append(
				TypeID(resource_id)
			)
	return stale


def _acl_resource_ref(chunk: Chunk) -> tuple[ResourceType, TypeID] | None:
	resource_type = chunk.metadata.get("resource_type")
	if not isinstance(resource_type, str):
		return None
	try:
		chunk_type = VectorChunkResourceType(resource_type)
	except ValueError:
		return None
	access_type = VECTOR_CHUNK_ACCESS_RESOURCE_TYPES.get(chunk_type)
	if access_type is None:
		return None
	id_key = (
		"parent_resource_id"
		if chunk_type in VECTOR_CHUNK_PARENT_RESOURCE_TYPES
		else "resource_id"
	)
	resource_id = chunk.metadata.get(id_key)
	if not isinstance(resource_id, str):
		return None
	return (access_type, TypeID(resource_id))


async def _stale_acl_resource_refs(
	db: AsyncSession,
) -> list[tuple[ResourceType, TypeID]]:
	chunks = await scroll_chunks(
		resource_types_filter(list(VECTOR_CHUNK_ACCESS_RESOURCE_TYPES)),
		db,
		payload_fields=_STALE_SCAN_PAYLOAD_FIELDS,
	)
	chunks_by_ref: dict[tuple[ResourceType, TypeID], list[Chunk]] = {}
	for chunk in chunks:
		if resource_ref := _acl_resource_ref(chunk):
			chunks_by_ref.setdefault(resource_ref, []).append(chunk)
	if not chunks_by_ref:
		return []
	# the stamp aggregates the resource's own revision with its ancestors', so a
	# rule change on any ancestor makes the expected value differ and repairs
	# every descendant chunk without the ACL write having walked the subtree.
	ids_by_type: dict[ResourceType, list[str]] = {}
	for resource_type, resource_id in chunks_by_ref:
		ids_by_type.setdefault(resource_type, []).append(str(resource_id))
	revisions: dict[tuple[ResourceType, TypeID], int] = {}
	for resource_type, resource_ids in ids_by_type.items():
		for resource_id, revision in (
			await fetch_bulk_acl_revisions(resource_ids, resource_type, db)
		).items():
			revisions[(resource_type, TypeID(resource_id))] = revision
	return [
		resource_ref
		for resource_ref, resource_chunks in chunks_by_ref.items()
		if any(
			chunk.metadata.get(ACL_REVISION_KEY) != revisions.get(resource_ref, 0)
			for chunk in resource_chunks
		)
	]


def _merge_acl_refs_into_stale_ids(
	stale_ids: dict[VectorChunkResourceType, list[TypeID]],
	resource_refs: list[tuple[ResourceType, TypeID]],
) -> None:
	for resource_type, resource_id in resource_refs:
		chunk_types = ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES.get(resource_type)
		if chunk_types is None:
			continue
		direct_type = next(
			chunk_type
			for chunk_type in chunk_types
			if chunk_type not in VECTOR_CHUNK_PARENT_RESOURCE_TYPES
		)
		ids = stale_ids.setdefault(direct_type, [])
		if resource_id not in ids:
			ids.append(resource_id)
