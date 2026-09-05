"""file-level (filename + description) vector plumbing."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.file import File
from api.permissions import ResourceType
from api.schemas.file import FileUpdate
from api.v1.service.authorization import fetch_bulk_acl_metadata
from api.v1.service.embeddings import embed_texts
from api.v1.service.files.metadata import (
	FILE_CONTENT_RESOURCE_TYPE,
	FILE_RESOURCE_TYPE,
	file_metadata,
	file_searchable_text,
)
from api.v1.service.files.text_contents import vectorize_file_content
from api.v1.service.vectorize import VectorSpec, build_chunk
from api.v1.service.vectorstores import (
	delete,
	parent_resource_filter,
	resource_types_filter,
	upsert_chunks,
)
from nokodo_ai.utils.typeid import TypeID


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
)


async def remove_file_vectors(
	file_id: str,
	session: AsyncSession,
	include_file_vector: bool = True,
	include_content_vectors: bool = True,
) -> None:
	"""remove file-level and/or file-content vectors for a file."""
	if include_file_vector:
		await delete(
			target=resource_types_filter(
				[FILE_RESOURCE_TYPE],
				resource_id=file_id,
			),
			session=session,
		)
	if include_content_vectors:
		await delete(
			target=parent_resource_filter(
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
	acl_metadata = (
		await fetch_bulk_acl_metadata([str(file.id)], ResourceType.FILE, session)
	)[str(file.id)]
	embedding = (
		precomputed_embedding
		if precomputed_embedding is not None
		else (await embed_texts([text], session, input_type="document"))[0]
	)
	chunk = build_chunk(FILE_SPEC, file, embedding, extra_metadata=acl_metadata)
	await upsert_chunks(chunks=[chunk], session=session)
	return 1


async def replace_all_file_vectors(file: File, session: AsyncSession) -> int:
	"""replace both description and content vectors for a file."""
	description_count = await replace_file_description_vectors(file, session)
	# content bytes are unchanged here, so only force=True rebuilds the chunks
	# carrying the acl/project metadata that just changed.
	batch = await vectorize_file_content(file, session, force=True)
	return description_count + len(batch.chunks)


async def vectorize_file_descriptions(
	session: AsyncSession,
	ids: list[TypeID] | None = None,
) -> int:
	"""rebuild description vectors for files; ids=None means every non-deleted
	file. returns count."""
	if ids is not None and not ids:
		return 0
	stmt = (
		select(File)
		.where(File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	if ids is not None:
		stmt = stmt.where(File.id.in_([str(fid) for fid in ids]))
	result = await session.execute(stmt)
	count = 0
	for file in result.scalars().all():
		count += await replace_file_description_vectors(file, session)
	return count
