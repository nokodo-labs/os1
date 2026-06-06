"""Open WebUI import service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.main import async_session_local, safe_rollback
from api.models.file import File
from api.models.project import Project
from api.open_webui import OpenWebUIAuthError, OpenWebUIClient, OpenWebUIError
from api.permissions import ActionPermission
from api.settings import OpenWebUIDeployment, settings
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.integrations.open_webui.chats import (
	ModelAgentResolver,
	_chat_folder_id,
	_chat_id,
	_chat_owui_file_ids,
	_chat_pinned,
	_import_one_chat,
)
from api.v1.service.integrations.open_webui.common import (
	ImportSummary,
	_client_error_to_http_exception,
	_first_str,
)
from api.v1.service.integrations.open_webui.deployments import (
	get_deployment,
	normalize_origin,
)
from api.v1.service.integrations.open_webui.folders import (
	_import_folder_projects,
	_import_pinned_chats_project,
)
from api.v1.service.integrations.open_webui.memories import _import_memories_chunk
from api.v1.service.integrations.open_webui.notes import _import_notes_chunk
from api.v1.service.memories import vectorize_memories
from api.v1.service.notes import vectorize_notes
from api.v1.service.threads import vectorize_threads
from api.v1.tasks.files import start_file_processing_task
from nokodo_ai.utils.concurrency import gather_bounded
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

type ImportProgressCallback = Callable[[int, str], Awaitable[None]]
type ChatImportMode = Literal["batched", "bulk"]


async def _report_progress(
	progress_callback: ImportProgressCallback | None,
	progress: int,
	stage: str,
) -> None:
	if progress_callback is not None:
		await progress_callback(progress, stage)


def _merge_import_summary(target: ImportSummary, source: ImportSummary) -> None:
	"""fold a worker's summary counters into the shared import summary."""
	target.chats_imported += source.chats_imported
	target.chats_skipped += source.chats_skipped
	target.messages_imported += source.messages_imported
	target.projects_imported += source.projects_imported
	target.projects_skipped += source.projects_skipped
	target.files_imported += source.files_imported
	target.files_skipped += source.files_skipped
	target.memories_imported += source.memories_imported
	target.memories_skipped += source.memories_skipped
	target.notes_imported += source.notes_imported
	target.notes_skipped += source.notes_skipped
	target.processing_file_ids.extend(source.processing_file_ids)
	target.memory_ids.extend(source.memory_ids)
	target.note_ids.extend(source.note_ids)
	target.thread_ids.extend(source.thread_ids)
	for error in source.errors or ():
		target.add_error(error)


def _chunked[ItemT](items: list[ItemT], chunks: int) -> list[list[ItemT]]:
	"""split items into at most ``chunks`` contiguous, near-even slices."""
	if not items:
		return []
	chunk_count = max(1, min(chunks, len(items)))
	size = -(-len(items) // chunk_count)
	return [items[start : start + size] for start in range(0, len(items), size)]


class _ProgressReporter:
	"""serialize progress callbacks so concurrent workers never overlap."""

	def __init__(self, callback: ImportProgressCallback | None) -> None:
		self._callback = callback
		self._lock = asyncio.Lock()

	async def report(self, progress: int, stage: str) -> None:
		if self._callback is None:
			return
		async with self._lock:
			await self._callback(progress, stage)


class _FileLockRegistry:
	"""per-Open-WebUI-file-id locks that serialize cross-chat file dedup."""

	def __init__(self) -> None:
		self._guard = asyncio.Lock()
		self._locks: dict[str, asyncio.Lock] = {}

	async def _lock_for(self, key: str) -> asyncio.Lock:
		async with self._guard:
			lock = self._locks.get(key)
			if lock is None:
				lock = asyncio.Lock()
				self._locks[key] = lock
			return lock

	@asynccontextmanager
	async def acquire(self, keys: Sequence[str]) -> AsyncIterator[None]:
		# acquire in a stable global order so chats sharing files cannot
		# deadlock against one another.
		async with AsyncExitStack() as stack:
			for key in sorted(set(keys)):
				lock = await self._lock_for(key)
				await stack.enter_async_context(lock)
			yield


class _PinnedProjectCache:
	"""lazily create the shared pinned-chats project exactly once."""

	def __init__(
		self,
		owner_id: TypeID,
		deployment: OpenWebUIDeployment,
	) -> None:
		self._owner_id = owner_id
		self._deployment = deployment
		self._lock = asyncio.Lock()
		self._project_id: TypeID | None = None

	async def ensure(self, summary: ImportSummary) -> TypeID:
		if self._project_id is not None:
			return self._project_id
		async with self._lock:
			if self._project_id is not None:
				return self._project_id
			async with async_session_local() as session:
				project = await _import_pinned_chats_project(
					session=session,
					owner_id=self._owner_id,
					deployment=self._deployment,
					summary=summary,
				)
				project_id = TypeID(project.id)
				await session.commit()
			self._project_id = project_id
		return self._project_id


def _require_import_permissions(
	principal: Principal,
	include_chats: bool,
	include_memories: bool,
	include_notes: bool,
) -> None:
	if include_chats:
		require_permission(principal, ActionPermission.THREADS_CREATE.value)
		require_permission(principal, ActionPermission.PROJECTS_CREATE.value)
		require_permission(principal, ActionPermission.FILES_CREATE.value)
	if include_memories:
		require_permission(principal, ActionPermission.MEMORIES_CREATE.value)
	if include_notes:
		require_permission(principal, ActionPermission.NOTES_CREATE.value)


async def _enqueue_imported_file_processing(
	session: AsyncSession,
	principal: Principal,
	summary: ImportSummary,
) -> None:
	"""enqueue async processing for files created during this import.

	runs after the import transaction has committed so each task sees a
	durably stored file. files whose nested transaction rolled back are
	skipped. failures are logged, never raised - a missed processing
	enqueue must not fail an otherwise successful import.
	"""
	file_ids = summary.processing_file_ids
	if not file_ids:
		return
	existing = set(
		(
			await session.scalars(
				select(File.id).where(
					File.id.in_([str(file_id) for file_id in file_ids]),
					File.deleted_at.is_(None),
				)
			)
		).all()
	)
	for file_id in file_ids:
		if str(file_id) not in existing:
			continue
		try:
			await start_file_processing_task(session, principal, file_id)
		except Exception:
			logger.exception(
				"failed to enqueue processing for imported file %s", file_id
			)


async def _vectorize_imported_resources(
	session: AsyncSession,
	summary: ImportSummary,
) -> None:
	"""vectorize resources created during this import.

	runs after the import transaction has committed so every resource is
	durably stored. memories and notes embed in batches; threads are
	vectorized from their title only - thread maintenance later generates a
	catalog summary and re-vectorizes. failures are logged, never raised - a
	vectorization gap must not fail an otherwise successful import.
	"""
	try:
		await vectorize_memories(summary.memory_ids, session)
	except Exception:
		logger.exception("failed to vectorize imported memories")
	try:
		await vectorize_notes(summary.note_ids, session)
	except Exception:
		logger.exception("failed to vectorize imported notes")
	try:
		await vectorize_threads(summary.thread_ids, session)
	except Exception:
		logger.exception("failed to vectorize imported threads")


async def _import_one_chat_worker(
	chat: dict[str, Any],
	chat_id: str,
	index: int,
	total: int,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	deployment_origin: str,
	client: OpenWebUIClient,
	folder_project_ids: dict[str, TypeID],
	pinned_cache: _PinnedProjectCache,
	model_resolver: ModelAgentResolver,
	file_locks: _FileLockRegistry,
	progress: _ProgressReporter,
) -> ImportSummary:
	"""import one chat in a dedicated session and commit it.

	files shared across chats are serialized by ``file_locks``, held across
	this chat's commit, so cross-chat file dedup stays correct under fan-out.
	"""
	local = ImportSummary(deployment_origin=deployment_origin)
	await progress.report(
		40 + int((index - 1) / total * 35),
		f"importing chat {index}/{total}",
	)
	file_ids = _chat_owui_file_ids(chat)
	# resolve the pinned project before opening this worker session so a worker
	# never holds two pool connections at once (its own session plus the cache's
	# dedicated session), which keeps fan-out deadlock-free near the pool limit.
	pinned_project_id: TypeID | None = None
	if _chat_pinned(chat):
		try:
			pinned_project_id = await pinned_cache.ensure(local)
		except Exception as exc:
			logger.exception("failed to import Open WebUI pinned chats project")
			local.add_error(f"pinned chats project failed: {type(exc).__name__}")
	async with async_session_local() as session:
		try:
			projects_by_folder_id: dict[str, Project] = {}
			folder_id = _chat_folder_id(chat)
			if folder_id is not None:
				folder_project_id = folder_project_ids.get(folder_id)
				if folder_project_id is not None:
					folder_project = await session.get(Project, folder_project_id)
					if folder_project is not None:
						projects_by_folder_id[folder_id] = folder_project
			pinned_project = (
				await session.get(Project, pinned_project_id)
				if pinned_project_id is not None
				else None
			)
			async with file_locks.acquire(file_ids):
				await _import_one_chat(
					chat,
					client=client,
					session=session,
					owner_id=owner_id,
					deployment=deployment,
					projects_by_folder_id=projects_by_folder_id,
					pinned_project=pinned_project,
					model_resolver=model_resolver,
					summary=local,
				)
				await session.commit()
		except Exception as exc:
			await safe_rollback(session)
			logger.exception("failed to import Open WebUI chat")
			local.chats_skipped += 1
			local.add_error(f"chat {chat_id} failed: {type(exc).__name__}")
	return local


async def _import_chat_items(
	chat_items: list[tuple[int, dict[str, Any], str]],
	total_chats: int,
	owner_id: TypeID,
	deployment: OpenWebUIDeployment,
	deployment_origin: str,
	client: OpenWebUIClient,
	folder_project_ids: dict[str, TypeID],
	pinned_cache: _PinnedProjectCache,
	model_resolver: ModelAgentResolver,
	file_locks: _FileLockRegistry,
	progress: _ProgressReporter,
	limit: int,
	summary: ImportSummary,
) -> None:
	"""fan out chat imports with bounded concurrency and merge the results."""
	if not chat_items:
		return
	results = await gather_bounded(
		(
			_import_one_chat_worker(
				chat,
				chat_id,
				index,
				total_chats,
				owner_id=owner_id,
				deployment=deployment,
				deployment_origin=deployment_origin,
				client=client,
				folder_project_ids=folder_project_ids,
				pinned_cache=pinned_cache,
				model_resolver=model_resolver,
				file_locks=file_locks,
				progress=progress,
			)
			for index, chat, chat_id in chat_items
		),
		limit=limit,
	)
	for result in results:
		_merge_import_summary(summary, result)


async def _fetch_chat_batch(
	client: OpenWebUIClient,
	batch_refs: list[dict[str, Any]],
	batch_start: int,
	fetch_concurrency: int,
	summary: ImportSummary,
) -> list[tuple[int, dict[str, Any], str]]:
	"""fetch one batch of chat bodies, merging each with its ref."""
	batch_items: list[tuple[int, dict[str, Any], str]] = []
	for offset, chat_ref in enumerate(batch_refs):
		chat_id = _first_str(chat_ref, "id", "chat_id")
		if chat_id is None:
			summary.chats_skipped += 1
			summary.add_error("chat skipped: missing Open WebUI id")
			continue
		batch_items.append((batch_start + offset + 1, chat_ref, chat_id))
	if not batch_items:
		return []
	fetch_results = await gather_bounded(
		(client.get_chat(chat_id) for _, _, chat_id in batch_items),
		limit=fetch_concurrency,
		return_exceptions=True,
	)
	chat_items: list[tuple[int, dict[str, Any], str]] = []
	for (index, chat_ref, chat_id), fetch_result in zip(
		batch_items, fetch_results, strict=True
	):
		if isinstance(fetch_result, OpenWebUIAuthError):
			raise _client_error_to_http_exception(fetch_result) from fetch_result
		if isinstance(fetch_result, asyncio.CancelledError):
			raise fetch_result
		if isinstance(fetch_result, OpenWebUIError):
			summary.chats_skipped += 1
			summary.add_error(f"chat {chat_id} fetch failed: {fetch_result}")
			continue
		if isinstance(fetch_result, BaseException):
			summary.chats_skipped += 1
			summary.add_error(
				f"chat {chat_id} fetch failed: {type(fetch_result).__name__}"
			)
			continue
		chat_body = fetch_result
		if chat_body is None:
			summary.chats_skipped += 1
			summary.add_error(f"chat {chat_id} skipped: empty response")
			continue
		chat = {**chat_ref, **chat_body}
		if chat_ref.get("archived") is True:
			chat["archived"] = True
		chat_items.append((index, chat, chat_id))
	return chat_items


async def import_from_open_webui(
	deployment_origin: str,
	credential: str,
	include_chats: bool,
	include_memories: bool,
	session: AsyncSession,
	principal: Principal,
	include_notes: bool = False,
	include_archived_chats: bool = False,
	chat_import_mode: ChatImportMode = "batched",
	progress_callback: ImportProgressCallback | None = None,
) -> ImportSummary:
	"""run a full import from an Open WebUI deployment for the current principal."""
	if not credential or not credential.strip():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Open WebUI credential is required",
		)
	if not (include_chats or include_memories or include_notes):
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="select at least one of chats, memories, or notes to import",
		)
	_require_import_permissions(
		principal,
		include_chats=include_chats,
		include_memories=include_memories,
		include_notes=include_notes,
	)

	deployment = get_deployment(deployment_origin)
	origin = normalize_origin(str(deployment.origin))
	summary = ImportSummary(deployment_origin=origin)
	owner_id = TypeID(principal.user.id)
	write_concurrency = settings.integrations.open_webui.db_write_concurrency

	async with OpenWebUIClient(origin=origin, credential=credential) as client:
		if include_chats:
			model_resolver = ModelAgentResolver(session=session, client=client)
			await _report_progress(progress_callback, 15, "loading folders")
			try:
				folders = await client.list_folders()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"folders fetch failed: {exc}")
				folders = []
			await _report_progress(progress_callback, 22, "importing folder projects")
			projects_by_folder_id: dict[str, Project] = {}
			try:
				projects_by_folder_id = await _import_folder_projects(
					folders,
					session=session,
					owner_id=owner_id,
					deployment=deployment,
					summary=summary,
				)
			except Exception as exc:
				await session.rollback()
				logger.exception("failed to import Open WebUI folders")
				summary.add_error(f"folders import failed: {type(exc).__name__}")
				projects_by_folder_id = {}

			pinned_cache = _PinnedProjectCache(owner_id=owner_id, deployment=deployment)
			file_locks = _FileLockRegistry()
			chat_progress = _ProgressReporter(progress_callback)

			if chat_import_mode == "bulk":
				await _report_progress(
					progress_callback, 30, "loading chats via bulk export"
				)
				try:
					chats = await client.list_bulk_chats(
						include_archived_chats=include_archived_chats
					)
				except OpenWebUIError as exc:
					raise _client_error_to_http_exception(exc) from exc
				total_chats = len(chats)
				await _report_progress(
					progress_callback, 35, f"found {total_chats} chats"
				)
				bulk_items: list[tuple[int, dict[str, Any], str]] = []
				for index, chat in enumerate(chats, start=1):
					chat_id = _chat_id(chat)
					if chat_id is None:
						summary.chats_skipped += 1
						summary.add_error("chat skipped: missing Open WebUI id")
						continue
					bulk_items.append((index, chat, chat_id))
				if total_chats:
					await model_resolver.prewarm()
				folder_project_ids = {
					folder_id: TypeID(project.id)
					for folder_id, project in projects_by_folder_id.items()
				}
				# durably persist the principal and pre-created projects so the
				# per-chat worker sessions (separate connections) can see them.
				await session.commit()
				await _import_chat_items(
					bulk_items,
					total_chats=total_chats,
					owner_id=owner_id,
					deployment=deployment,
					deployment_origin=origin,
					client=client,
					folder_project_ids=folder_project_ids,
					pinned_cache=pinned_cache,
					model_resolver=model_resolver,
					file_locks=file_locks,
					progress=chat_progress,
					limit=write_concurrency,
					summary=summary,
				)
			else:
				await _report_progress(progress_callback, 30, "loading chat list")
				try:
					chat_refs = await client.list_chat_refs(
						include_archived_chats=include_archived_chats
					)
				except OpenWebUIError as exc:
					raise _client_error_to_http_exception(exc) from exc
				total_chats = len(chat_refs)
				await _report_progress(
					progress_callback, 35, f"found {total_chats} chats"
				)
				if total_chats:
					await model_resolver.prewarm()
				folder_project_ids = {
					folder_id: TypeID(project.id)
					for folder_id, project in projects_by_folder_id.items()
				}
				# durably persist the principal and pre-created projects so the
				# per-chat worker sessions (separate connections) can see them.
				await session.commit()
				fetch_concurrency = settings.integrations.open_webui.fetch_concurrency
				for batch_start in range(0, total_chats, fetch_concurrency):
					batch_refs = chat_refs[
						batch_start : batch_start + fetch_concurrency
					]
					batch_progress = 40 + int(batch_start / total_chats * 35)
					await _report_progress(
						progress_callback,
						batch_progress,
						(
							"loading chats "
							f"{batch_start + 1}-"
							f"{batch_start + len(batch_refs)}/{total_chats}"
						),
					)
					batch_items = await _fetch_chat_batch(
						client=client,
						batch_refs=batch_refs,
						batch_start=batch_start,
						fetch_concurrency=fetch_concurrency,
						summary=summary,
					)
					await _import_chat_items(
						batch_items,
						total_chats=total_chats,
						owner_id=owner_id,
						deployment=deployment,
						deployment_origin=origin,
						client=client,
						folder_project_ids=folder_project_ids,
						pinned_cache=pinned_cache,
						model_resolver=model_resolver,
						file_locks=file_locks,
						progress=chat_progress,
						limit=write_concurrency,
						summary=summary,
					)
			await _report_progress(progress_callback, 78, "chats imported")

		if include_memories:
			await _report_progress(progress_callback, 82, "loading memories")
			try:
				memories = await client.list_memories()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"memories fetch failed: {exc}")
				memories = []
			await _report_progress(progress_callback, 86, "importing memories")
			# durably persist the principal so worker sessions can see it.
			await session.commit()
			memory_results = await gather_bounded(
				(
					_import_memories_chunk(
						chunk,
						owner_id=owner_id,
						deployment=deployment,
						deployment_origin=origin,
					)
					for chunk in _chunked(list(memories), write_concurrency)
				),
				limit=write_concurrency,
			)
			for memory_result in memory_results:
				_merge_import_summary(summary, memory_result)
			await _report_progress(progress_callback, 88, "memories imported")

		if include_notes:
			await _report_progress(progress_callback, 89, "loading notes")
			try:
				notes = await client.list_notes()
			except OpenWebUIAuthError as exc:
				raise _client_error_to_http_exception(exc) from exc
			except OpenWebUIError as exc:
				summary.add_error(f"notes fetch failed: {exc}")
				notes = []
			await _report_progress(progress_callback, 91, "importing notes")
			# durably persist the principal so worker sessions can see it.
			await session.commit()
			note_results = await gather_bounded(
				(
					_import_notes_chunk(
						chunk,
						owner_id=owner_id,
						deployment=deployment,
						deployment_origin=origin,
					)
					for chunk in _chunked(list(notes), write_concurrency)
				),
				limit=write_concurrency,
			)
			for note_result in note_results:
				_merge_import_summary(summary, note_result)
			await _report_progress(progress_callback, 93, "notes imported")

	await session.commit()
	await _enqueue_imported_file_processing(session, principal, summary)
	await _vectorize_imported_resources(session, summary)
	await _report_progress(progress_callback, 95 if include_notes else 90, "finalizing")
	return summary
