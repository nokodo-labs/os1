"""file processing durable tasks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.redis import on_invalidation
from api.settings import settings
from api.taskiq import broker, redis_schedule_source
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, load_principal_for_user
from api.v1.service.files.processing import (
	FILE_PROCESSING_TASK,
	list_files_due_for_processing,
	process_file,
	start_file_processing_task,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


FILE_PROCESSING_DISPATCH_TASK = "file.processing.dispatch"
FILE_MAINTENANCE_BACKFILL_TASK = "file.maintenance.backfill_sweep"
FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID = "file:maintenance-backfill"
FILE_MAINTENANCE_BACKFILL_INVALIDATION_SIGNAL = "file_maintenance_backfill"

_STALE_FILE_TASKS = (FILE_PROCESSING_TASK,)


def _file_task_runner_timeout_seconds() -> float:
	return float(settings.tasks.file_maintenance.runner_timeout_seconds)


def _file_stale_task_cleanup_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.file_maintenance.stale_task_cleanup_after_minutes
	)


async def fail_stale_file_tasks() -> int:
	"""fail file processing tasks that stopped reporting before they block work.

	a worker that dies mid-run (or during a connection-pool exhaustion event)
	can leave a file task stuck RUNNING. its file stays PENDING and the sweep's
	active-task guard then skips that file forever. failing the stale task frees
	the file to be redispatched on the next sweep.
	"""
	return await task_service.fail_stale_active_tasks(
		_STALE_FILE_TASKS,
		_file_stale_task_cleanup_after(),
		"file processing task stopped reporting progress",
	)


def _file_processing_schedule_id(file_id: TypeID) -> str:
	return f"file:processing:{file_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


async def schedule_file_processing_task(
	file_id: TypeID,
	user_id: TypeID,
	run_at: datetime,
	origin_session_id: str | None = None,
) -> None:
	"""schedule future file processing dispatch for one file."""
	if boot_settings.TESTING:
		return
	await (
		dispatch_file_processing.kicker()
		.with_schedule_id(_file_processing_schedule_id(file_id))
		.schedule_by_time(
			redis_schedule_source,
			_ceil_to_minute(run_at.astimezone(UTC)),
			str(file_id),
			str(user_id),
			origin_session_id,
		)
	)


@task_service.register_task_runner(
	FILE_PROCESSING_TASK,
	timeout_seconds=_file_task_runner_timeout_seconds,
)
async def run_file_processing_task(context: task_service.TaskContext) -> JSONObject:
	"""run both file processing pipelines for a file."""
	file_id = _file_id_from_context(context)
	origin_session_value = context.metadata.get("origin_session_id")
	origin_session_id = (
		origin_session_value if isinstance(origin_session_value, str) else None
	)
	await context.update(progress=10, stage="processing file")
	async with async_session_local() as session:
		result = await process_file(
			file_id,
			session,
			origin_session_id=origin_session_id,
		)
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return result


@broker.task(task_name=FILE_PROCESSING_DISPATCH_TASK)
async def dispatch_file_processing(
	file_id: str,
	user_id: str,
	origin_session_id: str | None = None,
) -> None:
	"""scheduled dispatcher that creates the durable file processing task."""
	async with async_session_local() as session:
		principal = await load_principal_for_user(TypeID(user_id), session)
		await start_file_processing_task(
			session,
			principal,
			TypeID(file_id),
			origin_session_id=origin_session_id,
		)
		await session.commit()


def _file_id_from_context(context: task_service.TaskContext) -> TypeID:
	file_id_value = context.metadata.get("file_id")
	if not isinstance(file_id_value, str) or not file_id_value:
		raise ValueError("file_id metadata is required")
	return TypeID(file_id_value)


# retroactive file maintenance backfill
#
# some files end up persisted without their deferred processing done. imports
# are the usual cause: they persist files but defer content vectorization and
# description generation so a bulk import does not stampede the embedding and
# chat model providers into rate limits (see the Open WebUI import service).
# the sweep below drains that backlog in bounded batches, dispatching one
# unified `file.process` task per due file so provider spend stays paced. all
# knobs come from `settings.tasks.file_maintenance`.


async def run_file_maintenance_backfill_sweep(
	batch_size: int | None = None,
	respect_enabled: bool = True,
) -> JSONObject:
	"""dispatch deferred processing for files with unfinished upkeep.

	this is the shared core for both the scheduled task and any manual
	trigger. callers control whether the master enabled flag is honored via
	`respect_enabled`; set False to spot-check the feature without leaving the
	schedule on.

	one backlog is drained per run, capped at the batch size: files that never
	recorded a content fingerprint or never got a description. files with an
	active processing task are skipped so a slow run is not piled onto.

	args:
		batch_size: override the configured batch size for this run.
		respect_enabled: when True, returns immediately if the master toggle
			is off.

	returns a JSON-friendly result describing how many tasks were dispatched
	and how many files were skipped for an already-active task.
	"""
	if respect_enabled:
		settings.reload()
	backfill_settings = settings.tasks.file_maintenance
	if respect_enabled and not backfill_settings.enabled:
		logger.info(
			"file maintenance backfill sweep skipped reason=disabled schedule_id=%s",
			FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID,
		)
		return {"skipped": True, "reason": "disabled", "dispatched": 0}

	effective_batch = (
		batch_size if batch_size is not None else backfill_settings.batch_size
	)
	if effective_batch <= 0:
		logger.warning(
			"file maintenance backfill sweep skipped reason=invalid_bounds "
			"batch_size=%d",
			effective_batch,
		)
		return {"skipped": True, "reason": "invalid_bounds", "dispatched": 0}

	# reap tasks that died mid-run first so their files stop being skipped by
	# the active-task guard below.
	await fail_stale_file_tasks()

	dispatched = 0
	skipped_existing = 0
	principals: dict[str, Principal] = {}
	async with async_session_local() as session:

		async def _principal_for(owner_id: TypeID) -> Principal:
			cached = principals.get(str(owner_id))
			if cached is None:
				cached = await load_principal_for_user(owner_id, session)
				principals[str(owner_id)] = cached
			return cached

		due_files = await list_files_due_for_processing(session, limit=effective_batch)
		for file in due_files:
			file_id = TypeID(file.id)
			existing = await task_service.find_active_task(
				session, FILE_PROCESSING_TASK, {"file_id": str(file_id)}
			)
			if existing is not None:
				skipped_existing += 1
				continue
			principal = await _principal_for(TypeID(file.owner_id))
			await start_file_processing_task(session, principal, file_id)
			dispatched += 1

	logger.info(
		"file maintenance backfill swept dispatched=%d skipped_existing=%d",
		dispatched,
		skipped_existing,
	)
	return {
		"dispatched": dispatched,
		"skipped_existing": skipped_existing,
		"batch_size": effective_batch,
	}


@broker.task(task_name=FILE_MAINTENANCE_BACKFILL_TASK)
async def dispatch_file_maintenance_backfill_sweep() -> JSONObject:
	"""scheduled entrypoint for the deferred file maintenance backfill.

	running this task is gated on
	`settings.tasks.file_maintenance.enabled`. when disabled it
	returns a `skipped` result so the tick does no work and spends no model
	tokens.
	"""
	return await run_file_maintenance_backfill_sweep(respect_enabled=True)


async def reconcile_file_maintenance_backfill_schedule() -> bool:
	"""install or remove the backfill cron schedule based on settings.

	called at API boot and again whenever the cache invalidation signal
	`file_maintenance_backfill` fires. the function is idempotent: it always
	deletes the existing schedule first, then installs a new one when the
	feature is enabled. returns True if a schedule is currently installed
	after the reconcile, False otherwise.
	"""
	if boot_settings.TESTING:
		return False
	settings.reload()
	await redis_schedule_source.delete_schedule(FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	backfill_settings = settings.tasks.file_maintenance
	if not backfill_settings.enabled:
		logger.info("file maintenance backfill schedule cleared (disabled)")
		return False
	try:
		await (
			dispatch_file_maintenance_backfill_sweep.kicker()
			.with_schedule_id(FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID)
			.schedule_by_cron(redis_schedule_source, backfill_settings.cron)
		)
	except ValueError as exc:
		logger.warning(
			"file maintenance backfill cron rejected by taskiq: %s (cron=%r)",
			exc,
			backfill_settings.cron,
		)
		return False
	logger.info(
		"file maintenance backfill schedule installed cron=%r batch_size=%d",
		backfill_settings.cron,
		backfill_settings.batch_size,
	)
	return True


async def clear_disabled_file_maintenance_backfill_schedule() -> bool:
	"""remove any persisted backfill schedule before TaskIQ startup when disabled."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	backfill_settings = settings.tasks.file_maintenance
	if backfill_settings.enabled:
		return False
	await redis_schedule_source.delete_schedule(FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	logger.info(
		"file maintenance backfill schedule cleared before taskiq startup "
		"reason=disabled schedule_id=%s",
		FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID,
	)
	return True


def _on_file_maintenance_backfill_settings_invalidation() -> None:
	"""react to a settings update by reconciling the backfill schedule.

	the cache invalidation pubsub handler is sync, so we hand the async
	reconcile off to the running event loop without blocking the listener.
	"""
	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		logger.debug("backfill invalidation received outside an event loop; skipping")
		return
	loop.create_task(reconcile_file_maintenance_backfill_schedule())


on_invalidation(
	FILE_MAINTENANCE_BACKFILL_INVALIDATION_SIGNAL,
	_on_file_maintenance_backfill_settings_invalidation,
)
