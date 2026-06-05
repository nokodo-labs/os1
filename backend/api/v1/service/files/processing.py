"""file processing orchestration."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.event_types import EventType
from api.models.file import File, FileStatus
from api.permissions import ResourceType
from api.v1.service.files.content_vectorization import (
	vectorize_file_content,
)
from api.v1.service.files.description import update_file_description
from api.v1.service.files.events import emit_file_event
from api.v1.service.files.vectorization import replace_file_description_vectors
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def process_file(
	file_id: TypeID,
	session: AsyncSession,
	origin_session_id: str | None = None,
) -> JSONObject:
	"""run description processing and content vectorization for a file."""
	file = await _load_file(file_id, session)
	file.status = FileStatus.PENDING
	await session.flush()
	await emit_file_event(
		session,
		event_type=EventType.FILE_PROCESSING,
		file_id=TypeID(file.id),
		user_id=TypeID(file.owner_id),
		filename=file.filename,
		project_ids=file.project_ids,
		origin_session_id=origin_session_id,
	)
	try:
		content_batch = await vectorize_file_content(file, session)
		await update_file_description(
			file, session, content_chunks=content_batch.chunks
		)
		await replace_file_description_vectors(file, session)
		file.status = FileStatus.AVAILABLE
		await session.flush()
		await invalidate_resource_payload_cache(ResourceType.FILE, TypeID(file.id))
		await emit_file_event(
			session,
			event_type=EventType.FILE_READY,
			file_id=TypeID(file.id),
			user_id=TypeID(file.owner_id),
			filename=file.filename,
			project_ids=file.project_ids,
			origin_session_id=origin_session_id,
		)
		return {
			"file_id": str(file.id),
			"content_chunks": len(content_batch.chunks),
			"text_loadable": content_batch.text_loadable,
			"skipped_reason": content_batch.skipped_reason,
		}
	except Exception:
		file.status = FileStatus.PENDING
		await session.flush()
		logger.exception("file processing failed for file %s", file.id)
		raise


async def process_file_description(
	file_id: TypeID,
	session: AsyncSession,
) -> JSONObject:
	"""repeat only the file-to-description-field pipeline."""
	file = await _load_file(file_id, session)
	description = await update_file_description(file, session)
	await replace_file_description_vectors(file, session)
	return {"file_id": str(file.id), "description_updated": description is not None}


async def process_file_content_vectorization(
	file_id: TypeID,
	session: AsyncSession,
) -> JSONObject:
	"""repeat only the file content vectorization pipeline."""
	file = await _load_file(file_id, session)
	batch = await vectorize_file_content(file, session)
	return {
		"file_id": str(file.id),
		"content_chunks": len(batch.chunks),
		"text_loadable": batch.text_loadable,
		"skipped_reason": batch.skipped_reason,
	}


async def _load_file(file_id: TypeID, session: AsyncSession) -> File:
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one_or_none()
	if file is None:
		raise ValueError(f"file not found: {file_id}")
	return file
