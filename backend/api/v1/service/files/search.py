"""file search service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import build_cursor_page, decode_cursor
from api.database.main import session_scope
from api.models.access_rule import AccessLevel
from api.models.file import File
from api.permissions import ResourceType
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	resource_access_predicate,
	vector_acl_filter,
)
from api.v1.service.embeddings import embed_text
from api.v1.service.files.metadata import FILE_CONTENT_RESOURCE_TYPE, file_metadata
from api.v1.service.files.vectorization import FILE_SPEC
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


_VECTOR_OVERFETCH_FACTOR = 4
_MAX_MATCHED_CHUNKS = 3
_PREVIEW_CHARS = 300
_MATCHED_CHUNK_PREVIEW_CHARS = 500


@dataclass(slots=True)
class _FileHitGroup:
	resource_id: str
	hits: list[ChunkSearchResult] = field(default_factory=list)

	@property
	def best_score(self) -> float | None:
		if not self.hits:
			return None
		return max(hit.score for hit in self.hits)

	@property
	def best_hit(self) -> ChunkSearchResult | None:
		if not self.hits:
			return None
		return max(self.hits, key=lambda hit: hit.score)


async def search_files(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> CursorPage[SearchResultItem]:
	params = search_params or SearchParams()
	coros: list[Awaitable[list[SearchResultItem]]] = []
	should_run_autocomplete = params.mode in (
		SearchMode.AUTOCOMPLETE,
		SearchMode.FULL,
	)
	should_run_hybrid = params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	)

	async def run_hybrid() -> list[SearchResultItem]:
		async with session_scope(None) as search_session:
			return await _hybrid_search_files(
				query_text,
				search_session,
				principal=principal,
				limit=limit + 1,
				search_params=params,
				query_embedding=query_embedding,
			)

	async def run_autocomplete() -> list[SearchResultItem]:
		async with session_scope(None) as search_session:
			return await _autocomplete_files(
				query_text,
				search_session,
				principal=principal,
				limit=limit + 1,
			)

	if should_run_hybrid:
		coros.append(run_hybrid())
	if should_run_autocomplete:
		coros.append(run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results,
		limit + 1,
		resource_name="files",
	)
	if cursor:
		timestamp, cursor_id = decode_cursor(cursor)
		items = [
			item
			for item in items
			if (item.updated_at, str(item.id)) < (timestamp, cursor_id)
		]
	if params.mode == SearchMode.AUTOCOMPLETE:
		items.sort(key=lambda item: (item.updated_at, str(item.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=FILE_SPEC.sort_key)


async def _autocomplete_files(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	pattern = contains_pattern(q)
	score = func.greatest(
		func.similarity(func.coalesce(File.filename, ""), q),
		func.similarity(func.coalesce(File.description, ""), q),
	)
	stmt = (
		select(File)
		.where(
			File.deleted_at.is_(None),
			resource_access_predicate(
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			),
			or_(
				score > 0.1,
				File.filename.ilike(pattern, escape="\\"),
				File.description.ilike(pattern, escape="\\"),
			),
		)
		.order_by(score.desc(), File.updated_at.desc())
		.limit(limit)
		.options(selectinload(File.projects))
	)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.FILE,
			id=TypeID(file.id),
			title=file.filename or "file",
			preview=file.description[:100] if file.description else None,
			metadata=file_metadata(file),
			created_at=file.created_at,
			updated_at=file.updated_at,
		)
		for file in result.scalars().all()
	]


async def _hybrid_search_files(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
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
	vector_limit = max(limit, limit * _VECTOR_OVERFETCH_FACTOR)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=vector_limit,
		query_filter=vector_acl_filter(
			[FILE_SPEC.resource_type, FILE_CONTENT_RESOURCE_TYPE],
			principal,
		),
		normalize=params.normalize,
	)
	if not results:
		return []
	groups = _group_file_hits(results)
	resource_ids = list(groups.keys())
	stmt = (
		select(File)
		.where(
			File.id.in_(resource_ids),
			File.deleted_at.is_(None),
			resource_access_predicate(
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			),
		)
		.options(selectinload(File.projects))
	)
	db_result = await db.execute(stmt)
	by_id = {str(file.id): file for file in db_result.scalars().all()}
	items: list[SearchResultItem] = []
	for resource_id in resource_ids:
		file = by_id.get(resource_id)
		if file is None:
			continue
		group = groups[resource_id]
		items.append(
			SearchResultItem(
				type=SearchResultType.FILE,
				id=TypeID(file.id),
				title=file.filename or "file",
				preview=_preview_for_group(file, group),
				score=group.best_score,
				metadata=_metadata_for_group(file, group),
				created_at=file.created_at,
				updated_at=file.updated_at,
			)
		)
		if len(items) >= limit:
			break
	return items


def _group_file_hits(results: list[ChunkSearchResult]) -> dict[str, _FileHitGroup]:
	groups: dict[str, _FileHitGroup] = {}
	for result in results:
		resource_id_value = _file_id_for_hit(result)
		if not isinstance(resource_id_value, str) or not resource_id_value:
			continue
		group = groups.setdefault(
			resource_id_value,
			_FileHitGroup(resource_id=resource_id_value),
		)
		group.hits.append(result)
	return groups


def _file_id_for_hit(hit: ChunkSearchResult) -> str | None:
	"""resolve the file id represented by a file or file_content hit."""
	if hit.metadata.get("resource_type") == FILE_CONTENT_RESOURCE_TYPE.value:
		parent_id = hit.metadata.get("parent_resource_id")
		return parent_id if isinstance(parent_id, str) else None
	resource_id = hit.metadata.get("resource_id")
	return resource_id if isinstance(resource_id, str) else None


def _preview_for_group(file: File, group: _FileHitGroup) -> str | None:
	best_hit = group.best_hit
	if best_hit is not None and best_hit.content:
		return best_hit.content[:_PREVIEW_CHARS]
	if file.description:
		return file.description[:_PREVIEW_CHARS]
	return None


def _metadata_for_group(file: File, group: _FileHitGroup) -> JSONObject:
	metadata = file_metadata(file)
	metadata["matched_chunks"] = [
		_matched_chunk_payload(hit)
		for hit in sorted(group.hits, key=lambda item: item.score, reverse=True)[
			:_MAX_MATCHED_CHUNKS
		]
	]
	return metadata


def _matched_chunk_payload(hit: ChunkSearchResult) -> JSONObject:
	chunk_metadata = hit.metadata
	payload: JSONObject = {
		"score": hit.score,
		"preview": hit.content[:_MATCHED_CHUNK_PREVIEW_CHARS],
	}
	for key in (
		"resource_type",
		"chunk_index",
		"chunk_count",
		"page_number",
		"slide_number",
		"section_label",
		"paragraph_index",
		"line_start",
		"line_end",
		"column_start",
		"column_end",
		"char_start",
		"char_end",
		"text_loader",
		"chunking_algorithm",
	):
		value = chunk_metadata.get(key)
		if value is not None:
			payload[key] = value
	return payload
