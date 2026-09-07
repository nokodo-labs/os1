"""file processing orchestration."""

import logging

from sqlalchemy import or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from api.constants import PRIVATE_METADATA_KEY
from api.database import async_session_local
from api.models.event_types import EventType
from api.models.file import File, FileSource, FileStatus
from api.models.task import Task, TaskType
from api.permissions import ResourceType
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.embeddings import embed_texts
from api.v1.service.files.description import (
	build_file_description,
	update_file_description,
)
from api.v1.service.files.events import emit_file_event
from api.v1.service.files.text_contents import (
	CONTENT_VECTOR_COLLECTION_KEY,
	CONTENT_VECTOR_FINGERPRINT_KEY,
	file_content_config_fp,
	file_content_stale_predicate,
	has_extracted_text_child,
	load_file_content_chunks_reusing_stored_text,
	store_extracted_text,
	vectorize_file_content,
)
from api.v1.service.files.vectorization import (
	replace_all_file_vectors,
	replace_file_description_vectors,
)
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.tasks import (
	find_active_task,
	start_task,
)
from api.v1.service.vectorize import StaleBy
from api.v1.service.vectorstores import get_collection
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# file sources the content pipeline ingests as primary content; its own
# derivatives are excluded so it never reprocesses its outputs.
CONTENT_PIPELINE_SOURCES = frozenset(
	{
		FileSource.USER_UPLOADED,
		FileSource.AGENT_GENERATED,
		FileSource.USER_IMPORTED,
	}
)


# durable task names shared between the enqueue helpers below and their runners.
FILE_PROCESSING_TASK = "file.process"


async def start_file_processing_task(
	session: AsyncSession,
	principal: Principal,
	file_id: TypeID,
	origin_session_id: str | None = None,
	force: bool = False,
) -> Task:
	"""enqueue both fundamental file processing pipelines."""
	metadata: JSONObject = {"file_id": str(file_id)}
	if origin_session_id is not None:
		metadata["origin_session_id"] = origin_session_id
	if force:
		metadata["force"] = True
	existing = await find_active_task(
		session,
		FILE_PROCESSING_TASK,
		{"file_id": str(file_id)},
	)
	if existing is not None:
		return existing
	return await start_task(
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
	force: bool = False,
) -> JSONObject:
	"""run description processing and content vectorization for a file."""
	file = await _load_file(file_id, session)
	file.status = FileStatus.PENDING
	await session.flush()
	await emit_file_event(
		session,
		event_type=EventType.FILE_PROCESSING,
		file_id=file.id,
		user_id=file.owner_id,
		filename=file.filename,
		project_ids=file.project_ids,
		origin_session_id=origin_session_id,
	)
	try:
		content_batch = await vectorize_file_content(file, session, force=force)
		fresh = content_batch.skipped_reason != "already_current"
		needs_description = file.description is None
		needs_extracted_text = not fresh and not await has_extracted_text_child(
			file.id, session
		)
		if not fresh and (needs_description or needs_extracted_text):
			content_batch = await load_file_content_chunks_reusing_stored_text(
				file, session
			)
		if needs_description:
			await update_file_description(
				file,
				session,
				content_chunks=content_batch.chunks,
				full_content=content_batch.content,
			)
		if fresh or needs_extracted_text:
			await store_extracted_text(file, content_batch.content, session)
		await replace_file_description_vectors(file, session)
		file.status = FileStatus.AVAILABLE
		await session.flush()
		await invalidate_resource_payload_cache(ResourceType.FILE, file.id)
		await emit_file_event(
			session,
			event_type=EventType.FILE_READY,
			file_id=file.id,
			user_id=file.owner_id,
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
		batch = await load_file_content_chunks_reusing_stored_text(file, session)
		await session.commit()

		# phase 2: external I/O, no Postgres connection held - the calls below
		# open their own short-lived sessions when their caches are cold.
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

	a file is due when it never recorded a content-vectorization fingerprint,
	never got an LLM description, or never stored its extracted body text,
	covering every half of the unified pipeline in one query. imports are the
	usual source of this backlog because they persist files AVAILABLE but defer
	processing so a bulk import never stampedes the embedding and chat model
	providers. stranded PENDING files (their processing task died) are included
	too; the sweep's active-task guard keeps freshly uploaded files with a live
	task from being redispatched. results are ordered oldest-first and
	SQL-limited so each sweep drains at most one batch.
	"""
	child = aliased(File)
	missing_extracted_text = ~(
		select(child.id)
		.where(
			child.parent_file_id == File.id,
			child.source == FileSource.TEXT_EXTRACTION,
			child.deleted_at.is_(None),
		)
		.exists()
	)
	conditions = [
		File.metadata_[(PRIVATE_METADATA_KEY, CONTENT_VECTOR_FINGERPRINT_KEY)]
		.as_string()
		.is_(None),
		File.description.is_(None),
		missing_extracted_text,
	]
	collection = await get_collection(session)
	collection_text = File.metadata_[
		(PRIVATE_METADATA_KEY, CONTENT_VECTOR_COLLECTION_KEY)
	].as_string()
	conditions.extend(
		[
			collection_text.is_(None),
			collection_text != collection,
		]
	)
	triggers = settings.assets.revectorize.file_contents
	if triggers.on_pipeline_version:
		conditions.append(file_content_stale_predicate(StaleBy.PIPELINE_VERSION))
	if triggers.on_config_change:
		conditions.append(
			file_content_stale_predicate(
				StaleBy.CONFIG,
				config_fp=await file_content_config_fp(session),
			)
		)
	stmt = (
		select(File)
		.where(
			File.deleted_at.is_(None),
			File.source.in_(CONTENT_PIPELINE_SOURCES),
			File.status.in_((FileStatus.PENDING, FileStatus.AVAILABLE)),
			or_(*conditions),
		)
		.order_by(File.created_at.asc())
		.limit(limit)
	)
	return list((await session.execute(stmt)).scalars().all())


async def vectorize_files(
	session: AsyncSession,
	ids: list[TypeID] | None = None,
) -> int:
	"""rebuild description and content vectors for content-pipeline files.

	ids=None means every content-pipeline file. returns count processed.
	"""
	if ids is not None and not ids:
		return 0
	stmt = (
		select(File)
		.where(File.deleted_at.is_(None), File.source.in_(CONTENT_PIPELINE_SOURCES))
		.options(selectinload(File.projects))
	)
	if ids is not None:
		stmt = stmt.where(File.id.in_([str(fid) for fid in ids]))
	processed = 0
	for file in (await session.execute(stmt)).scalars().all():
		try:
			await replace_all_file_vectors(file, session)
		except Exception:
			logger.exception("file vector rebuild failed for file %s", file.id)
			continue
		processed += 1
	return processed


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
