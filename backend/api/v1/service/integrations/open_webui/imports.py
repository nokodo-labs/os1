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
from api.v1.tasks.files import start_file_content_vectorization_task
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
	"""enqueue content vectorization for files created during this import.

	runs after the import transaction has committed so each task sees a
	durably stored file. files whose nested transaction rolled back are
	skipped. failures are logged, never raised - a missed processing
	enqueue must not fail an otherwise successful import.

	only content vectorization is enqueued here. LLM description generation
	is deliberately NOT triggered inline: a large import creates hundreds of
	files at once, and fanning out a description task per file stampedes the
	chat model provider into rate limits. descriptions are instead filled in
	gradually by the throttled file description backfill sweep.
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
			await start_file_content_vectorization_task(session, principal, file_id)
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


async def _import_chats_streaming(
	chat_list: list[Any],
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
	fetch_concurrency: int,
	write_concurrency: int,
	summary: ImportSummary,
) -> None:
	"""fetch and import chats in one overlapping producer/consumer pipeline.

	the previous batched approach fetched a full window of chat bodies, then
	imported that window, then fetched the next - so the network fetch pool
	and the database write pool never ran at the same time and every batch
	stalled on its slowest chat. here a fetch pool (sized by
	``fetch_concurrency``) streams chat bodies into a bounded queue while a
	write pool (sized by ``write_concurrency``) drains it, so both stages stay
	saturated for the whole import.
	"""
	refs: list[tuple[int, dict[str, Any], str]] = []
	for offset, chat_ref in enumerate(chat_list):
		chat_id = _first_str(chat_ref, "id", "chat_id")
		if chat_id is None:
			summary.chats_skipped += 1
			summary.add_error("chat skipped: missing Open WebUI id")
			continue
		refs.append((offset + 1, chat_ref, chat_id))
	if not refs:
		return

	# a bounded queue applies backpressure so the fetch pool never races far
	# ahead of the slower write pool and buffers the whole export in memory.
	queue: asyncio.Queue[tuple[int, dict[str, Any], str] | None] = asyncio.Queue(
		maxsize=max(fetch_concurrency, write_concurrency) * 2
	)
	merge_lock = asyncio.Lock()

	async def _merge(local: ImportSummary) -> None:
		async with merge_lock:
			_merge_import_summary(summary, local)

	async def _record_skip(detail: str) -> None:
		local = ImportSummary(deployment_origin=deployment_origin)
		local.chats_skipped += 1
		local.add_error(detail)
		await _merge(local)

	async def _fetch_one(index: int, chat_ref: dict[str, Any], chat_id: str) -> None:
		try:
			chat_body = await client.get_chat(chat_id)
		except OpenWebUIAuthError as exc:
			# auth failures are fatal for the whole import; propagate so the
			# fetch pool cancels and the caller surfaces a clear error.
			raise _client_error_to_http_exception(exc) from exc
		except OpenWebUIError as exc:
			await _record_skip(f"chat {chat_id} fetch failed: {exc}")
			return
		if chat_body is None:
			await _record_skip(f"chat {chat_id} skipped: empty response")
			return
		chat = {**chat_ref, **chat_body}
		if chat_ref.get("archived") is True:
			chat["archived"] = True
		await queue.put((index, chat, chat_id))

	async def _produce() -> None:
		try:
			await gather_bounded(
				(_fetch_one(index, ref, cid) for index, ref, cid in refs),
				limit=fetch_concurrency,
			)
		finally:
			# wake every consumer exactly once so they drain and exit, even
			# when a fatal fetch error short-circuits the fetch pool.
			for _ in range(write_concurrency):
				await queue.put(None)

	async def _consume() -> None:
		while True:
			item = await queue.get()
			if item is None:
				return
			index, chat, chat_id = item
			local = await _import_one_chat_worker(
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
			await _merge(local)

	consumers = [asyncio.create_task(_consume()) for _ in range(write_concurrency)]
	try:
		await _produce()
	finally:
		# the producer's own finally enqueues one sentinel per consumer, so
		# every consumer drains remaining committed work and exits cleanly even
		# when the fetch pool short-circuited on a fatal error. awaiting here
		# guarantees that, then any fatal fetch error re-raises after cleanup.
		await asyncio.gather(*consumers)


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
		# phase 1: fetch all API data concurrently.
		# list_* calls are independent HTTP requests to the OWUI server and
		# typically dominate wall time, especially bulk chat export or large
		# memory/note lists.
		await _report_progress(progress_callback, 10, "fetching data from open webui")

		_coro_keys: list[str] = []
		_coros = []
		if include_chats:
			_coro_keys.append("folders")
			_coros.append(client.list_folders())
			_coro_keys.append("chat_list")
			if chat_import_mode == "bulk":
				_coros.append(
					client.list_bulk_chats(
						include_archived_chats=include_archived_chats
					)
				)
			else:
				_coros.append(
					client.list_chat_refs(include_archived_chats=include_archived_chats)
				)
		if include_memories:
			_coro_keys.append("memories")
			_coros.append(client.list_memories())
		if include_notes:
			_coro_keys.append("notes")
			_coros.append(client.list_notes())

		_raw = await asyncio.gather(*_coros, return_exceptions=True) if _coros else []
		_fetch = dict(zip(_coro_keys, _raw))

		# re-raise any CancelledError captured by return_exceptions
		for _v in _fetch.values():
			if isinstance(_v, asyncio.CancelledError):
				raise _v

		folders: list[Any] = []
		chat_list: list[Any] = []
		memories: list[Any] = []
		notes: list[Any] = []

		if include_chats:
			_fr = _fetch["folders"]
			if isinstance(_fr, OpenWebUIAuthError):
				raise _client_error_to_http_exception(_fr) from _fr
			elif isinstance(_fr, OpenWebUIError):
				summary.add_error(f"folders fetch failed: {_fr}")
			elif isinstance(_fr, list):
				folders = _fr

			_cl = _fetch["chat_list"]
			if isinstance(_cl, OpenWebUIError):
				raise _client_error_to_http_exception(_cl) from _cl
			elif isinstance(_cl, BaseException):
				raise RuntimeError(f"chat list fetch failed: {_cl}") from _cl
			elif isinstance(_cl, list):
				chat_list = _cl

		if include_memories:
			_mr = _fetch["memories"]
			if isinstance(_mr, OpenWebUIAuthError):
				raise _client_error_to_http_exception(_mr) from _mr
			elif isinstance(_mr, OpenWebUIError):
				summary.add_error(f"memories fetch failed: {_mr}")
			elif isinstance(_mr, list):
				memories = _mr

		if include_notes:
			_nr = _fetch["notes"]
			if isinstance(_nr, OpenWebUIAuthError):
				raise _client_error_to_http_exception(_nr) from _nr
			elif isinstance(_nr, OpenWebUIError):
				summary.add_error(f"notes fetch failed: {_nr}")
			elif isinstance(_nr, list):
				notes = _nr

		_parts: list[str] = []
		if include_chats:
			_parts.append(f"{len(chat_list)} chats")
		if include_memories:
			_parts.append(f"{len(memories)} memories")
		if include_notes:
			_parts.append(f"{len(notes)} notes")
		await _report_progress(progress_callback, 20, f"found {', '.join(_parts)}")

		# phase 2: import chats (dominant cost; workers emit progress in 40-75)
		if include_chats:
			model_resolver = ModelAgentResolver(session=session, client=client)
			await _report_progress(progress_callback, 22, "setting up folder projects")
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
			folder_project_ids = {
				folder_id: TypeID(project.id)
				for folder_id, project in projects_by_folder_id.items()
			}
			# durably persist principal and pre-created projects so per-chat
			# worker sessions (separate connections) can see them.
			await session.commit()

			if chat_import_mode == "bulk":
				bulk_items: list[tuple[int, dict[str, Any], str]] = []
				for index, chat in enumerate(chat_list, start=1):
					chat_id = _chat_id(chat)
					if chat_id is None:
						summary.chats_skipped += 1
						summary.add_error("chat skipped: missing Open WebUI id")
						continue
					bulk_items.append((index, chat, chat_id))
				total_bulk = len(bulk_items)
				await _report_progress(
					progress_callback, 25, f"importing {total_bulk} chats"
				)
				if total_bulk:
					await model_resolver.prewarm()
				await _import_chat_items(
					bulk_items,
					total_chats=total_bulk,
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
				total_chats = len(chat_list)
				await _report_progress(
					progress_callback, 25, f"importing {total_chats} chats"
				)
				if total_chats:
					await model_resolver.prewarm()
				fetch_concurrency = settings.integrations.open_webui.fetch_concurrency
				await _import_chats_streaming(
					chat_list,
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
					fetch_concurrency=fetch_concurrency,
					write_concurrency=write_concurrency,
					summary=summary,
				)
			await _report_progress(progress_callback, 85, "chats imported")

		# phase 3: write memories + notes in parallel; each chunk uses its own
		# session internally so these are safe to run concurrently.
		if include_memories or include_notes:
			_mem_notes_start = 85 if include_chats else 25
			_what = (
				"importing memories and notes"
				if include_memories and include_notes
				else "importing memories"
				if include_memories
				else "importing notes"
			)
			await _report_progress(progress_callback, _mem_notes_start, _what)
			# durably persist principal so worker sessions can see it.
			await session.commit()

			async def _write_memories() -> list[ImportSummary]:
				if not memories:
					return []
				return await gather_bounded(
					(
						_import_memories_chunk(
							chunk,
							owner_id=owner_id,
							deployment=deployment,
							deployment_origin=origin,
						)
						for chunk in _chunked(memories, write_concurrency)
					),
					limit=write_concurrency,
				)

			async def _write_notes() -> list[ImportSummary]:
				if not notes:
					return []
				return await gather_bounded(
					(
						_import_notes_chunk(
							chunk,
							owner_id=owner_id,
							deployment=deployment,
							deployment_origin=origin,
						)
						for chunk in _chunked(notes, write_concurrency)
					),
					limit=write_concurrency,
				)

			mem_write_results, note_write_results = await asyncio.gather(
				_write_memories(),
				_write_notes(),
			)
			for r in mem_write_results:
				_merge_import_summary(summary, r)
			for r in note_write_results:
				_merge_import_summary(summary, r)
			await _report_progress(progress_callback, 88, "all resources imported")

	await session.commit()
	await _enqueue_imported_file_processing(session, principal, summary)
	await _report_progress(progress_callback, 90, "vectorizing resources")
	await _vectorize_imported_resources(session, summary)
	await _report_progress(progress_callback, 99, "finalizing")
	return summary
