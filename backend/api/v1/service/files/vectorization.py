"""file vectorization plumbing."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.file import File
from api.permissions import ResourceType
from api.schemas.file import FileUpdate
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.authorization import fetch_acl_metadata, fetch_bulk_acl_metadata
from api.v1.service.embeddings import embed_texts
from api.v1.service.files.metadata import (
	FILE_CONTENT_RESOURCE_TYPE,
	FILE_RESOURCE_TYPE,
	file_metadata,
	file_searchable_text,
)
from api.v1.service.vectorize import VectorSpec, build_chunk
from nokodo_ai.adapters.base.vectorstores import Chunk
from nokodo_ai.types.json import JSONObject, JSONValue


logger = logging.getLogger(__name__)


async def file_should_revectorize(
	file: File,
	file_in: FileUpdate,
	session: AsyncSession,
) -> bool:
	fields = {"filename", "description", "project_ids", "status"}
	update_data = file_in.model_dump(exclude_unset=True, mode="python")
	return bool(fields & update_data.keys())


FILE_SPEC: VectorSpec[File] = VectorSpec(
	resource_type=FILE_RESOURCE_TYPE,
	resource_id=lambda file: str(file.id),
	dense_text=file_searchable_text,
	bm25_text=file_searchable_text,
	metadata=file_metadata,
	should_revectorize=file_should_revectorize,
	sort_key="updated_at",
)


async def remove_file_vectors(
	file_id: str,
	session: AsyncSession,
	include_file_vector: bool = True,
	include_content_vectors: bool = True,
) -> None:
	"""remove file-level and/or file-content vectors for a file."""
	if include_file_vector:
		await vectorstore_service.delete(
			target=vectorstore_service.resource_types_filter(
				[FILE_RESOURCE_TYPE],
				resource_id=file_id,
			),
			session=session,
		)
	if include_content_vectors:
		await vectorstore_service.delete(
			target=vectorstore_service.parent_resource_filter(
				FILE_RESOURCE_TYPE,
				file_id,
				resource_types=[FILE_CONTENT_RESOURCE_TYPE],
			),
			session=session,
		)


async def replace_file_description_vectors(
	file: File,
	session: AsyncSession,
	precomputed_embedding: list[float] | None = None,
) -> int:
	"""replace the filename/description vector chunk for a file.

	when precomputed_embedding is supplied the embed_texts call is skipped so
	callers can pre-compute the embedding outside a DB session and avoid
	holding a connection during the embedding API round-trip.
	"""
	await remove_file_vectors(str(file.id), session, include_content_vectors=False)
	text = file_searchable_text(file)
	if not text:
		return 0
	acl_metadata = await fetch_acl_metadata(str(file.id), ResourceType.FILE, session)
	embedding = (
		precomputed_embedding
		if precomputed_embedding is not None
		else (await embed_texts([text], session))[0]
	)
	chunk = build_chunk(FILE_SPEC, file, embedding, extra_metadata=acl_metadata)
	await vectorstore_service.upsert_chunks(chunks=[chunk], session=session)
	return 1


async def replace_all_file_vectors(file: File, session: AsyncSession) -> int:
	"""replace both description and content vectors for a file."""
	from api.v1.service.files.content_vectorization import vectorize_file_content

	description_count = await replace_file_description_vectors(file, session)
	batch = await vectorize_file_content(file, session)
	return description_count + len(batch.chunks)


async def vectorize_all_files(session: AsyncSession) -> int:
	"""rebuild vectors for all files. returns file count processed."""
	stmt = (
		select(File)
		.where(File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	result = await session.execute(stmt)
	processed = 0
	for file in result.scalars().all():
		try:
			await replace_all_file_vectors(file, session)
		except Exception:
			logger.exception("file vector rebuild failed for file %s", file.id)
			continue
		processed += 1
	return processed


async def vectorize_file_descriptions_bulk(session: AsyncSession) -> int:
	"""legacy-compatible bulk description vectorization."""
	stmt = (
		select(File)
		.where(File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	result = await session.execute(stmt)
	valid: list[tuple[File, str]] = []
	for file in result.scalars().all():
		text = file_searchable_text(file)
		if text:
			valid.append((file, text))
	if not valid:
		return 0
	file_ids = [str(file.id) for file, _text in valid]
	acl_by_id = await fetch_bulk_acl_metadata(file_ids, ResourceType.FILE, session)
	embeddings = await embed_texts([text for _file, text in valid], session)
	chunks = [
		build_chunk(
			FILE_SPEC,
			file,
			embedding,
			extra_metadata=acl_by_id.get(str(file.id)),
		)
		for (file, text), embedding in zip(valid, embeddings)
	]
	for file, _text in valid:
		await remove_file_vectors(str(file.id), session, include_content_vectors=False)
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


def _build_file_content_chunk(
	file: File,
	content: str,
	embedding: list[float],
	chunk_index: int,
	chunk_count: int,
	extra_metadata: Mapping[str, object] | None = None,
) -> Chunk:
	"""build a vector chunk for extracted file body content."""
	metadata: JSONObject = {
		"resource_type": FILE_CONTENT_RESOURCE_TYPE.value,
		"parent_resource_type": FILE_RESOURCE_TYPE.value,
		"parent_resource_id": str(file.id),
		"owner_id": str(file.owner_id),
		"chunk_index": chunk_index,
		"chunk_count": chunk_count,
	}
	metadata.update(_json_metadata(extra_metadata))
	return Chunk(
		id=str(uuid.uuid4()),
		content=content,
		embedding=embedding,
		metadata=metadata,
	)


def _json_metadata(values: Mapping[str, object] | None) -> JSONObject:
	metadata: JSONObject = {}
	if values is None:
		return metadata
	for key, value in values.items():
		json_value = _json_value(value)
		if json_value is not None:
			metadata[key] = json_value
	return metadata


def _json_value(value: object) -> JSONValue | None:
	if value is None or isinstance(value, (str, int, float, bool)):
		return value
	if isinstance(value, list):
		items: list[JSONValue] = []
		for item in value:
			json_item = _json_value(item)
			if json_item is not None:
				items.append(json_item)
		return items
	if isinstance(value, dict):
		nested: JSONObject = {}
		for key, item in value.items():
			json_item = _json_value(item)
			if json_item is not None:
				nested[str(key)] = json_item
		return nested
	return str(value)
