"""file search service."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.database.main import session_scope
from api.models.access_rule import AccessLevel
from api.models.file import File
from api.models.project import Project
from api.permissions import ResourceType
from api.schemas.file import FileSearchFilters
from api.schemas.search import (
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
from api.v1.service.search.grouping import group_resource_hits
from api.v1.service.search.primitives import ScoredResult, merge_scored
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


_VECTOR_OVERFETCH_FACTOR = 4
_MAX_MATCHED_CHUNKS = 3
_MATCHED_CHUNK_PREVIEW_CHARS = 500


def _file_search_conditions(
	filters: FileSearchFilters | None,
) -> list[vectorstore_service.FieldCondition]:
	"""vector-layer narrowing conditions derived from file search filters."""
	conditions: list[vectorstore_service.FieldCondition] = []
	if filters is None:
		return conditions
	if filters.owner_id is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="owner_id", value=str(filters.owner_id))
		)
	if filters.source is not None:
		conditions.append(
			vectorstore_service.FieldMatch(key="source", value=filters.source.value)
		)
	if filters.project_id is not None:
		conditions.append(
			vectorstore_service.FieldMatch(
				key="project_ids", value=str(filters.project_id)
			)
		)
	return conditions


def _apply_file_search_filters(
	stmt: Select,
	filters: FileSearchFilters | None,
) -> Select:
	"""SQL-layer narrowing mirroring _file_search_conditions."""
	if filters is None:
		return stmt
	if filters.include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	if filters.owner_id is not None:
		stmt = stmt.where(File.owner_id == str(filters.owner_id))
	if filters.source is not None:
		stmt = stmt.where(File.source == filters.source)
	if filters.project_id is not None:
		stmt = stmt.where(File.projects.any(Project.id == str(filters.project_id)))
	return stmt


def file_to_search_item(
	file: File,
	score: float | None = None,
) -> SearchResultItem:
	"""projection from a file (and optional score) to a SearchResultItem."""
	return SearchResultItem(
		type=SearchResultType.FILE,
		id=TypeID(file.id),
		title=file.filename or "file",
		preview=file.description[:100] if file.description else None,
		score=score,
		metadata=file_metadata(file),
		created_at=file.created_at,
		updated_at=file.updated_at,
	)


async def search_files(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	offset: int = 0,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	score_threshold: float = 0.0,
	filters: FileSearchFilters | None = None,
) -> list[ScoredResult[File]]:
	"""relevance-ordered, deduped file hits with internal scores.

	hybrid tier ranks first; autocomplete-only matches are appended.
	"""
	params = search_params or SearchParams()
	if filters and filters.include_deleted:
		if not principal.is_admin:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		if params.mode != SearchMode.AUTOCOMPLETE:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="include_deleted requires autocomplete search mode",
			)
	if params.mode == SearchMode.AUTOCOMPLETE:
		async with session_scope(None) as search_session:
			return await _autocomplete_files(
				query_text,
				search_session,
				principal=principal,
				limit=limit,
				offset=offset,
				filters=filters,
			)
	fetch = offset + limit
	coros: list[Awaitable[list[ScoredResult[File]]]] = []
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

	async def run_hybrid() -> list[ScoredResult[File]]:
		async with session_scope(None) as search_session:
			return await _hybrid_search_files(
				query_text,
				search_session,
				principal=principal,
				limit=fetch,
				search_params=params,
				query_embedding=query_embedding,
				filters=filters,
			)

	async def run_autocomplete() -> list[ScoredResult[File]]:
		async with session_scope(None) as search_session:
			return await _autocomplete_files(
				query_text,
				search_session,
				principal=principal,
				limit=fetch,
				filters=filters,
			)

	if should_run_hybrid:
		coros.append(run_hybrid())
	if should_run_autocomplete:
		coros.append(run_autocomplete())
	results = await asyncio.gather(*coros, return_exceptions=True)
	merged = merge_scored(results, resource_name="files")
	if score_threshold > 0.0:
		merged = [s for s in merged if s.score >= score_threshold]
	return merged[offset : offset + limit]


async def _autocomplete_files(
	q: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 5,
	offset: int = 0,
	filters: FileSearchFilters | None = None,
) -> list[ScoredResult[File]]:
	"""pg_trgm autocomplete tier scored by filename/description similarity."""
	pattern = contains_pattern(q)
	sim = func.greatest(
		func.similarity(func.coalesce(File.filename, ""), q),
		func.similarity(func.coalesce(File.description, ""), q),
	)
	stmt = (
		select(File, sim.label("sim"))
		.where(
			resource_access_predicate(
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			),
			or_(
				sim > 0.1,
				File.filename.ilike(pattern, escape="\\"),
				File.description.ilike(pattern, escape="\\"),
			),
		)
		.order_by(sim.desc(), File.updated_at.desc())
		.offset(offset)
		.limit(limit)
		.options(selectinload(File.projects))
	)
	stmt = _apply_file_search_filters(stmt, filters)
	result = await db.execute(stmt)
	return [ScoredResult(item=file, score=float(score)) for file, score in result.all()]


async def _hybrid_search_files(
	query_text: str,
	db: AsyncSession,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
	filters: FileSearchFilters | None = None,
) -> list[ScoredResult[File]]:
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
		query_filter=vectorstore_service.with_conditions(
			vector_acl_filter(
				[FILE_SPEC.resource_type, FILE_CONTENT_RESOURCE_TYPE],
				principal,
			),
			_file_search_conditions(filters),
		),
		normalize=params.normalize,
	)
	if not results:
		return []
	groups = group_resource_hits(results, _file_id_for_hit)
	resource_ids = list(groups.keys())
	stmt = (
		select(File)
		.where(
			File.id.in_(resource_ids),
			resource_access_predicate(
				principal,
				ResourceType.FILE,
				required_level=AccessLevel.READER,
			),
		)
		.options(selectinload(File.projects))
	)
	stmt = _apply_file_search_filters(stmt, filters)
	db_result = await db.execute(stmt)
	by_id = {str(file.id): file for file in db_result.scalars().all()}
	scored: list[ScoredResult[File]] = []
	for resource_id in resource_ids:
		file = by_id.get(resource_id)
		if file is None:
			continue
		extra: JSONObject = {
			"matched_chunks": groups[resource_id].matched_chunks(
				_MAX_MATCHED_CHUNKS, _MATCHED_CHUNK_PREVIEW_CHARS
			)
		}
		scored.append(
			ScoredResult(
				item=file,
				score=groups[resource_id].best_score,
				extra=extra,
			)
		)
		if len(scored) >= limit:
			break
	return scored


def _file_id_for_hit(hit: ChunkSearchResult) -> str | None:
	"""resolve the file id represented by a file or file_content hit."""
	if hit.metadata.get("resource_type") == FILE_CONTENT_RESOURCE_TYPE.value:
		parent_id = hit.metadata.get("parent_resource_id")
		return parent_id if isinstance(parent_id, str) else None
	resource_id = hit.metadata.get("resource_id")
	return resource_id if isinstance(resource_id, str) else None
