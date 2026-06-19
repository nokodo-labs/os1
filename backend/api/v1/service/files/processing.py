"""file processing orchestration."""

from __future__ import annotations

import logging

from sqlalchemy import or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.models.event_types import EventType
from api.models.file import File, FileStatus
from api.models.task import Task, TaskType
from api.permissions import ResourceType
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal
from api.v1.service.embeddings import embed_texts
from api.v1.service.files.content_vectorization import (
	CONTENT_VECTOR_FINGERPRINT_KEY,
	load_file_content_chunks,
	vectorize_file_content,
)
from api.v1.service.files.description import (
	build_file_description,
	update_file_description,
)
from api.v1.service.files.events import emit_file_event
from api.v1.service.files.vectorization import replace_file_description_vectors
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


# durable task names shared between the enqueue helpers below and the runners
# that execute them in api.v1.tasks.files.
FILE_PROCESSING_TASK = "file.process"


async def start_file_processing_task(
	session: AsyncSession,
	principal: Principal,
	file_id: TypeID,
	origin_session_id: str | None = None,
) -> Task:
	"""enqueue both fundamental file processing pipelines."""
	metadata: JSONObject = {"file_id": str(file_id)}
	if origin_session_id is not None:
		metadata["origin_session_id"] = origin_session_id
	existing = await task_service.find_active_task(
		session,
		FILE_PROCESSING_TASK,
		{"file_id": str(file_id)},
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=FILE_PROCESSING_TASK,
		metadata=metadata,
		stage="queued file processing",
		progress=0,
	)


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
		if file.description is None:
			# vectors may already be current (cheap re-dispatch). re-load the
			# extracted text only to build the owed description; reusing the
			# current vectors avoids a redundant embed + upsert of content we
			# already stored.
			if content_batch.skipped_reason == "already_current":
				content_batch = await load_file_content_chunks(file, session)
			await update_file_description(
				file,
				session,
				content_chunks=content_batch.chunks,
				full_content=content_batch.content,
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
	preserve_timestamps: bool = False,
) -> JSONObject:
	"""run the description + vectorization pipeline for one file.

	uses a single DB session with an intermediate commit to avoid holding a
	connection during the LLM and embedding API calls:
		phase 1 (connection held briefly) - load file and content chunks, then
		commit to return the connection to the pool.
		phase 2 (no connection) - LLM description generation; compute the
		description embedding. both are external network calls that can take
		several seconds each and must not hold a Postgres connection.
		phase 3 (connection held briefly) - persist description and vector;
		all DB operations here are quick writes with no external calls.
	"""
	async with async_session_local() as session:
		# phase 1: load data, then release the connection
		file = await _load_file(file_id, session)
		batch = await load_file_content_chunks(file, session)
		await session.commit()

		# phase 2: external I/O - no Postgres connection held
		# build_file_description and embed_texts both use process-level caches
		# and open their own short-lived sessions if the cache is cold.
		description = await build_file_description(
			file, batch.chunks, full_content=batch.content
		)
		# vector text must include the new description so search finds the file
		desc_for_vector = description if description is not None else file.description
		vector_parts = [p for p in [file.filename or "", desc_for_vector or ""] if p]
		vector_text = " ".join(vector_parts).strip()
		embedding: list[float] = (
			(await embed_texts([vector_text], input_type="document"))[0]
			if vector_text
			else []
		)

		# phase 3: quick DB writes only - connection reacquired lazily
		description_updated = False
		if description is not None:
			if preserve_timestamps:
				await session.execute(
					sql_update(File)
					.where(File.id == file.id)
					.values(description=description)
					.execution_options(synchronize_session="evaluate")
				)
				file.description = description
			else:
				file.description = description
				await session.flush()
			description_updated = True
		await replace_file_description_vectors(
			file,
			session,
			precomputed_embedding=embedding if vector_text else None,
		)
		await session.commit()

	return {"file_id": str(file_id), "description_updated": description_updated}


async def list_files_due_for_processing(
	session: AsyncSession,
	limit: int,
) -> list[File]:
	"""return files that still owe deferred processing.

	a file is due when it never recorded a content-vectorization fingerprint
	or never got an LLM description, covering both halves of the unified
	pipeline in one query. imports are the usual source of this backlog
	because they persist files AVAILABLE but defer processing so a bulk import
	never stampedes the embedding and chat model providers. stranded PENDING
	files (their processing task died) are included too; the sweep's active-task
	guard keeps freshly uploaded files with a live task from being redispatched.
	results are ordered oldest-first and SQL-limited so each sweep drains at
	most one batch.
	"""
	stmt = (
		select(File)
		.where(
			File.deleted_at.is_(None),
			File.status.in_((FileStatus.PENDING, FileStatus.AVAILABLE)),
			or_(
				File.metadata_[CONTENT_VECTOR_FINGERPRINT_KEY].as_string().is_(None),
				File.description.is_(None),
			),
		)
		.order_by(File.created_at.asc())
		.limit(limit)
	)
	return list((await session.execute(stmt)).scalars().all())


async def _load_file(file_id: TypeID, session: AsyncSession) -> File:
	"""load a non-deleted file by id with its projects, raising if it is missing."""
	result = await session.execute(
		select(File)
		.where(File.id == file_id, File.deleted_at.is_(None))
		.options(selectinload(File.projects))
	)
	file = result.scalars().one_or_none()
	if file is None:
		raise ValueError(f"file not found: {file_id}")
	return file
