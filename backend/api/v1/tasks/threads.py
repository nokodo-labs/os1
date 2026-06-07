"""TaskIQ wrappers and schedules for durable thread-related work.

this module owns three orthogonal concerns:

1. durable runner registration for thread summarization, summary condensation,
   memory post-processing, and thread metadata maintenance. each runner is
   registered with `task_service.register_task_runner` and given an explicit
   timeout so a misbehaving runner cannot stay active forever.
2. dynamic, per-thread post-run maintenance. when a run completes, the chat
	service calls `schedule_thread_inactivity_maintenance`. missing mandatory
	metadata starts maintenance immediately; summary-only work writes a one-shot
	redis schedule using `settings.tasks.thread_maintenance.inactivity_hours`.
	API startup does not scan threads to recreate these timers.
3. an explicit, off-by-default retroactive backfill sweep. administrators can
   enable a periodic sweep via `settings.tasks.maintenance_backfill` or run
   one manually through the admin endpoint. each sweep is bounded by an
   explicit batch size and lookback window so model spend stays controlled.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.models.task import Task, TaskStatus, TaskType
from api.models.thread import Thread
from api.redis import on_invalidation
from api.settings import settings
from api.taskiq import broker, redis_schedule_source
from api.v1.service import memories as memory_service
from api.v1.service import tasks as task_service
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal, load_principal_for_user
from api.v1.service.chat.context_compaction.summarization import (
	SummaryRangeStaleError,
	condense_summaries,
	summarize_thread_message_range,
)
from api.v1.service.chat.message_references import wait_message_reference
from api.v1.service.chat.run_activities import start_detached_run_activity
from api.v1.service.events import build_live_persisting_event_emitter
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


CHAT_SUMMARIZE_MESSAGES_TASK = "chat.summarize_messages"
CHAT_CONDENSE_SUMMARIES_TASK = "chat.condense_summaries"
MEMORY_POST_PROCESSING_TASK = "memory.post_process"
THREAD_MAINTENANCE_TASK = "thread.maintenance"
THREAD_INACTIVITY_DISPATCH_TASK = "thread.inactivity.dispatch"
THREAD_MAINTENANCE_BACKFILL_TASK = "thread.maintenance.backfill_sweep"
THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID = "thread:maintenance-backfill"
THREAD_MAINTENANCE_BACKFILL_INVALIDATION_SIGNAL = "thread_maintenance_backfill"

_STALE_THREAD_RELATED_TASKS = (
	CHAT_SUMMARIZE_MESSAGES_TASK,
	CHAT_CONDENSE_SUMMARIES_TASK,
	MEMORY_POST_PROCESSING_TASK,
	THREAD_MAINTENANCE_TASK,
)


def _thread_maintenance_inactivity_hours() -> int:
	return settings.tasks.thread_maintenance.inactivity_hours


def _thread_maintenance_queued_supersede_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.queued_supersede_after_minutes
	)


def _thread_maintenance_active_supersede_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.active_supersede_after_minutes
	)


def _thread_task_runner_timeout_seconds() -> float:
	return float(settings.tasks.thread_maintenance.runner_timeout_seconds)


def _thread_stale_task_cleanup_after() -> timedelta:
	return timedelta(
		minutes=settings.tasks.thread_maintenance.stale_task_cleanup_after_minutes
	)


def _thread_inactivity_schedule_id(thread_id: TypeID) -> str:
	"""build the per-thread redis schedule id used by the inactivity timer.

	the id is stable so successive calls overwrite the same redis key, which
	lets `schedule_thread_inactivity_maintenance` reset an existing timer
	without leaking duplicate schedules.
	"""
	return f"thread:inactivity-maintenance:{thread_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	"""round a datetime up to the next whole minute.

	taskiq scheduler ticks at minute granularity. rounding up avoids the
	common off-by-one where a sub-minute due time would be picked up on the
	previous tick and fire slightly early.
	"""
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _ensure_aware_utc(value: datetime) -> datetime:
	"""force a datetime to be timezone-aware in UTC.

	legacy rows may carry naive datetimes; everything we schedule or
	compare against `datetime.now(tz=UTC)` must be aware.
	"""
	if value.tzinfo is None:
		return value.replace(tzinfo=UTC)
	return value.astimezone(UTC)


def _active_task_is_stale(task: Task, stale_after: timedelta) -> bool:
	"""whether an active task has stopped reporting progress for too long.

	used by `start_thread_maintenance_task` to supersede a hung active task
	instead of returning it to the caller forever.
	"""
	last_event_at = _task_last_event_at(task)
	if last_event_at is None:
		return False
	return datetime.now(tz=UTC) - last_event_at > stale_after


def _task_last_event_at(task: Task) -> datetime | None:
	last_event_at = task.last_event_at or task.updated_at or task.created_at
	if last_event_at is None:
		return None
	return _ensure_aware_utc(last_event_at)


def _active_queued_task_is_stale(task: Task, stale_after: timedelta) -> bool:
	if (task.progress or 0) != 0:
		return False
	if not (task.stage or "").lower().startswith("queued"):
		return False
	last_event_at = _task_last_event_at(task)
	if last_event_at is None:
		return False
	return datetime.now(tz=UTC) - last_event_at > stale_after


async def start_summarize_messages_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	start_message_id: TypeID,
	end_message_id: TypeID,
	branch_head_message_id: str | None = None,
) -> Task:
	"""enqueue durable summarization for a persisted thread message range."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"purpose": "agent_context",
		"start_message_id": str(start_message_id),
		"end_message_id": str(end_message_id),
	}
	if branch_head_message_id is not None:
		metadata["branch_head_message_id"] = branch_head_message_id
	existing = await task_service.find_active_task(
		session, CHAT_SUMMARIZE_MESSAGES_TASK, metadata
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=CHAT_SUMMARIZE_MESSAGES_TASK,
		metadata=metadata,
		stage="queued summarization",
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_condense_summaries_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	branch_head_message_id: str | None = None,
) -> Task:
	"""enqueue durable summary condensation for one thread."""
	metadata: JSONObject = {"thread_id": str(thread_id)}
	if branch_head_message_id is not None:
		metadata["branch_head_message_id"] = branch_head_message_id
	existing = await task_service.find_active_task(
		session, CHAT_CONDENSE_SUMMARIES_TASK, metadata
	)
	if existing is not None:
		return existing
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=CHAT_CONDENSE_SUMMARIES_TASK,
		metadata=metadata,
		stage="queued condensation",
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_memory_post_processing_task(
	session: AsyncSession,
	principal: Principal,
	query_text: str,
	max_related_memories: int,
	conversation_snapshot: str | None = None,
	thread_id: str | None = None,
	message_id: str | None = None,
	message_ref: str | None = None,
	run_id: str | None = None,
	emit_activity: bool = False,
) -> Task:
	"""enqueue durable memory maintenance for a conversation query."""
	runtime: JSONObject = {
		"query_text": query_text,
		"max_related_memories": max_related_memories,
		"conversation_snapshot": conversation_snapshot,
		"thread_id": thread_id,
		"message_id": message_id,
		"message_ref": message_ref,
		"run_id": run_id,
		"emit_activity": emit_activity,
	}
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=MEMORY_POST_PROCESSING_TASK,
		metadata={"query_length": len(query_text)},
		runtime=runtime,
		stage="queued memory processing",
		progress=0,
	)


async def start_thread_maintenance_task(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	observed_last_activity_at: datetime | None = None,
	replace_metadata: bool = False,
	origin_session_id: str | None = None,
	stage: str = "queued",
	source: str = "direct",
	reason: str = "requested",
) -> Task:
	"""enqueue durable metadata/summary maintenance for one thread."""
	metadata: JSONObject = {
		"thread_id": str(thread_id),
		"replace_metadata": replace_metadata,
		"maintenance_source": source,
		"maintenance_reason": reason,
	}
	if observed_last_activity_at is not None:
		metadata["observed_last_activity_at"] = observed_last_activity_at.isoformat()
		if reason != "mandatory_metadata":
			metadata["inactivity_hours"] = _thread_maintenance_inactivity_hours()
	if origin_session_id is not None:
		metadata["origin_session_id"] = origin_session_id
	existing = await task_service.find_active_task(
		session, THREAD_MAINTENANCE_TASK, {"thread_id": str(thread_id)}
	)
	if existing is not None:
		queued_stale = _active_queued_task_is_stale(
			existing, _thread_maintenance_queued_supersede_after()
		)
		if not queued_stale and not _active_task_is_stale(
			existing, _thread_maintenance_active_supersede_after()
		):
			logger.info(
				"thread maintenance enqueue skipped; active task exists "
				"thread_id=%s existing_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			return existing
		failure_result: JSONObject
		if queued_stale:
			logger.warning(
				"thread maintenance queued task is stale; superseding "
				"thread_id=%s queued_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			failure_stage = "queued task superseded"
			failure_result = {
				"error": "stale_queued_task",
				"message": "superseded after queued inactivity",
				"thread_id": str(thread_id),
			}
		else:
			logger.warning(
				"thread maintenance active task is stale; superseding "
				"thread_id=%s stale_task_id=%s user_id=%s source=%s reason=%s",
				thread_id,
				existing.id,
				principal.user.id,
				source,
				reason,
			)
			failure_stage = "stale task superseded"
			failure_result = {
				"error": "stale_active_task",
				"message": "superseded by a new thread maintenance task",
				"thread_id": str(thread_id),
			}
		await task_service.update_task_execution(
			TypeID(existing.id),
			status_value=TaskStatus.FAILED,
			stage=failure_stage,
			result=failure_result,
		)
	logger.info(
		"thread maintenance enqueue requested thread_id=%s user_id=%s "
		"source=%s reason=%s stage=%s replace_metadata=%s observed_last_activity_at=%s",
		thread_id,
		principal.user.id,
		source,
		reason,
		stage,
		replace_metadata,
		observed_last_activity_at.isoformat()
		if observed_last_activity_at is not None
		else None,
	)
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=THREAD_MAINTENANCE_TASK,
		metadata=metadata,
		stage=stage,
		progress=0,
		spawned_thread_id=thread_id,
	)


async def start_thread_inactivity_maintenance_task(
	session: AsyncSession,
	principal: Principal,
	thread: Thread,
	source: str = "inactivity_timer",
	reason: str = "inactivity_timer",
) -> Task:
	"""enqueue maintenance for one inactive thread observed by the timer."""
	return await start_thread_maintenance_task(
		session,
		principal,
		TypeID(thread.id),
		observed_last_activity_at=thread.last_activity_at,
		source=source,
		reason=reason,
	)


async def schedule_thread_inactivity_maintenance(
	thread_id: TypeID,
	session: AsyncSession | None = None,
	source: str = "post_run",
) -> bool:
	"""start mandatory work now or reset the deferred inactivity timer."""
	if boot_settings.TESTING:
		return False
	schedule_id = _thread_inactivity_schedule_id(thread_id)
	await redis_schedule_source.delete_schedule(schedule_id)

	async def schedule_with(active_session: AsyncSession) -> bool:
		thread = await active_session.get(Thread, thread_id)
		if thread is None:
			return False
		await active_session.refresh(thread)
		if thread.last_activity_at is None:
			return False
		if thread_service.thread_needs_mandatory_maintenance(thread):
			principal = await load_principal_for_user(
				TypeID(thread.owner_id), active_session
			)
			await start_thread_maintenance_task(
				active_session,
				principal,
				TypeID(thread.id),
				observed_last_activity_at=thread.last_activity_at,
				stage="queued mandatory metadata",
				source=source,
				reason="mandatory_metadata",
			)
			return True
		if not await thread_service.thread_needs_deferred_maintenance(
			thread,
			active_session,
		):
			return False
		last_activity_at = _ensure_aware_utc(thread.last_activity_at)
		due_at = last_activity_at + timedelta(
			hours=_thread_maintenance_inactivity_hours()
		)
		if due_at <= datetime.now(tz=UTC):
			return False
		await (
			dispatch_thread_inactivity_maintenance.kicker()
			.with_schedule_id(schedule_id)
			.schedule_by_time(
				redis_schedule_source,
				_ceil_to_minute(due_at),
				str(thread.id),
				last_activity_at.isoformat(),
			)
		)
		logger.info(
			"thread inactivity maintenance timer scheduled thread_id=%s "
			"schedule_id=%s source=%s due_at=%s observed_last_activity_at=%s",
			thread.id,
			schedule_id,
			source,
			_ceil_to_minute(due_at).isoformat(),
			last_activity_at.isoformat(),
		)
		return True

	if session is not None:
		return await schedule_with(session)
	async with async_session_local() as new_session:
		return await schedule_with(new_session)


async def delete_thread_inactivity_maintenance_schedule(thread_id: TypeID) -> None:
	"""delete the inactivity timer for a thread."""
	if boot_settings.TESTING:
		return
	await redis_schedule_source.delete_schedule(
		_thread_inactivity_schedule_id(thread_id)
	)


async def fail_stale_thread_related_tasks() -> int:
	"""fail old active model-backed tasks before they block new attempts."""
	return await task_service.fail_stale_active_tasks(
		_STALE_THREAD_RELATED_TASKS,
		_thread_stale_task_cleanup_after(),
		"thread-related task stopped reporting progress",
	)


@task_service.register_task_runner(
	CHAT_SUMMARIZE_MESSAGES_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_summarize_messages_task(context: task_service.TaskContext) -> JSONObject:
	"""run persisted message-range summarization."""
	thread_id_value = context.metadata.get("thread_id")
	start_value = context.metadata.get("start_message_id")
	end_value = context.metadata.get("end_message_id")
	branch_head_value = context.metadata.get("branch_head_message_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	if not isinstance(start_value, str) or not start_value:
		raise ValueError("start_message_id metadata is required")
	if not isinstance(end_value, str) or not end_value:
		raise ValueError("end_message_id metadata is required")
	branch_head_message_id = (
		TypeID(branch_head_value)
		if isinstance(branch_head_value, str) and branch_head_value
		else None
	)

	thread_id = TypeID(thread_id_value)
	await context.update(progress=10, stage="loading messages")
	async with async_session_local() as session:
		try:
			summary_id = await summarize_thread_message_range(
				thread_id=thread_id,
				start_message_id=TypeID(start_value),
				end_message_id=TypeID(end_value),
				branch_head_message_id=branch_head_message_id,
				session=session,
			)
		except SummaryRangeStaleError as exc:
			await context.update(progress=90, stage="summary range stale")
			return {
				"thread_id": str(thread_id),
				"summary_id": None,
				"skipped": True,
				"reason": str(exc),
			}
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return {"thread_id": str(thread_id), "summary_id": str(summary_id)}


@task_service.register_task_runner(
	CHAT_CONDENSE_SUMMARIES_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_condense_summaries_task(context: task_service.TaskContext) -> JSONObject:
	"""run summary condensation for one thread."""
	thread_id_value = context.metadata.get("thread_id")
	branch_head_value = context.metadata.get("branch_head_message_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	thread_id = TypeID(thread_id_value)
	branch_head_message_id = (
		TypeID(branch_head_value)
		if isinstance(branch_head_value, str) and branch_head_value
		else None
	)
	await context.update(progress=10, stage="loading summaries")
	async with async_session_local() as session:
		try:
			summary_id = await condense_summaries(
				thread_id=thread_id,
				expected_branch_head_message_id=branch_head_message_id,
				session=session,
			)
		except SummaryRangeStaleError as exc:
			await context.update(progress=90, stage="condensation range stale")
			return {
				"thread_id": str(thread_id),
				"summary_id": None,
				"skipped": True,
				"reason": str(exc),
			}
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return {
		"thread_id": str(thread_id),
		"summary_id": str(summary_id) if summary_id is not None else None,
		"skipped": summary_id is None,
	}


@task_service.register_task_runner(
	MEMORY_POST_PROCESSING_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_memory_post_processing_task(
	context: task_service.TaskContext,
) -> JSONObject:
	"""run memory maintenance for the owning user."""
	query_text = context.runtime.get("query_text")
	max_related_memories = context.runtime.get("max_related_memories")
	if not isinstance(query_text, str) or not query_text.strip():
		return {"skipped": True, "reason": "empty query"}
	if not isinstance(max_related_memories, int) or max_related_memories <= 0:
		max_related_memories = 10

	snapshot = context.runtime.get("conversation_snapshot")
	conversation_snapshot = snapshot if isinstance(snapshot, str) else None
	thread_id_value = context.runtime.get("thread_id")
	thread_id = thread_id_value if isinstance(thread_id_value, str) else None
	message_id_value = context.runtime.get("message_id")
	message_id = message_id_value if isinstance(message_id_value, str) else None
	message_ref_value = context.runtime.get("message_ref")
	message_ref = message_ref_value if isinstance(message_ref_value, str) else None
	run_id_value = context.runtime.get("run_id")
	run_id = run_id_value if isinstance(run_id_value, str) else None
	emit_activity = context.runtime.get("emit_activity") is True

	async def report_progress(progress: int, stage: str) -> None:
		await context.update(progress=progress, stage=stage)

	await context.update(progress=10, stage="starting memory processing")
	# resolve message_id before processing so newly created memories get
	# source_message_id set; wait_message_reference is a quick poll if the
	# message is already committed.
	if message_id is None and message_ref is not None:
		message_id = await wait_message_reference(message_ref)
	async with async_session_local() as session:
		principal = await load_principal_for_user(context.user_id, session)
		result = await memory_service.post_process_relevant_memories(
			query_text,
			session,
			principal=principal,
			max_related_memories=max_related_memories,
			conversation_snapshot=conversation_snapshot,
			progress_callback=report_progress,
			source_message_id=message_id,
		)
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	if emit_activity:
		await _emit_memory_maintenance_activity(
			result,
			user_id=str(context.user_id),
			thread_id=thread_id,
			message_id=message_id,
			run_id=run_id,
		)
	return result


def _activity_count(result: JSONObject, key: str) -> int:
	"""read an integer count from a memory maintenance result."""
	value = result.get(key)
	return value if isinstance(value, int) and not isinstance(value, bool) else 0


async def _emit_memory_maintenance_activity(
	result: JSONObject,
	user_id: str,
	thread_id: str | None,
	message_id: str | None,
	run_id: str | None,
) -> None:
	"""emit a memory_maintenance run activity when memories were changed."""
	created = _activity_count(result, "created")
	updated = _activity_count(result, "updated")
	deleted = _activity_count(result, "deleted")
	changed_kinds = sum(1 for count in (created, updated, deleted) if count > 0)
	if created + updated + deleted <= 0:
		return
	if thread_id is None or message_id is None or run_id is None:
		return

	emit = build_live_persisting_event_emitter()
	activity = await start_detached_run_activity(
		emit,
		user_id=user_id,
		thread_id=thread_id,
		run_id=run_id,
		activity_type="memory_maintenance",
		message_id=message_id,
		title="updating memory",
	)
	if activity is None:
		return
	if changed_kinds > 1:
		summary = "memories updated"
	elif created > 0:
		summary = "memory saved" if created == 1 else "memories saved"
	elif updated > 0:
		summary = "memory updated" if updated == 1 else "memories updated"
	else:
		summary = "memory removed" if deleted == 1 else "memories removed"
	await activity.ended(
		outcome="success",
		message=summary,
		data={
			"created": created,
			"updated": updated,
			"deleted": deleted,
		},
	)


@task_service.register_task_runner(
	THREAD_MAINTENANCE_TASK,
	timeout_seconds=_thread_task_runner_timeout_seconds,
)
async def run_thread_maintenance_task(context: task_service.TaskContext) -> JSONObject:
	"""run thread metadata and branch-summary maintenance."""
	thread_id_value = context.metadata.get("thread_id")
	if not isinstance(thread_id_value, str) or not thread_id_value:
		raise ValueError("thread_id metadata is required")
	thread_id = TypeID(thread_id_value)
	replace_metadata = context.metadata.get("replace_metadata") is True
	origin_session_value = context.metadata.get("origin_session_id")
	origin_session_id = (
		origin_session_value if isinstance(origin_session_value, str) else None
	)
	observed_value = context.metadata.get("observed_last_activity_at")
	observed_at: datetime | None = None
	if isinstance(observed_value, str) and observed_value:
		try:
			observed_at = datetime.fromisoformat(observed_value)
		except ValueError:
			observed_at = None
		if observed_at is not None and observed_at.tzinfo is None:
			observed_at = observed_at.replace(tzinfo=UTC)

	await context.check_cancelled()
	await context.update(progress=10, stage="checking")
	# live mandatory maintenance counts as activity; deferred/backfill does not
	maintenance_source = context.metadata.get("maintenance_source", "")
	update_activity = maintenance_source == "post_run"
	async with async_session_local() as session:
		thread = await session.get(Thread, thread_id)
		if thread is None:
			return {
				"thread_id": thread_id_value,
				"skipped": True,
				"reason": "not found",
			}
		principal = await load_principal_for_user(TypeID(thread.owner_id), session)
		await context.update(progress=45, stage="generating")
		result = await thread_service.maintain_thread_metadata(
			thread_id,
			session,
			principal=principal,
			observed_last_activity_at=observed_at,
			replace_metadata=replace_metadata,
			origin_session_id=origin_session_id,
			update_activity=update_activity,
		)
		await session.commit()
	await context.check_cancelled()
	await context.update(progress=90, stage="finalizing")
	return result


@broker.task(task_name=THREAD_INACTIVITY_DISPATCH_TASK)
async def dispatch_thread_inactivity_maintenance(
	thread_id: str,
	observed_last_activity_at: str,
) -> int:
	"""enqueue maintenance when a one-shot inactivity timer matures."""
	try:
		observed_at = datetime.fromisoformat(observed_last_activity_at)
	except ValueError:
		return 0
	observed_at = _ensure_aware_utc(observed_at)
	if datetime.now(tz=UTC) < observed_at + timedelta(
		hours=_thread_maintenance_inactivity_hours()
	):
		return 0
	async with async_session_local() as session:
		thread = await session.get(Thread, TypeID(thread_id))
		if thread is None:
			return 0
		if thread.last_activity_at is None:
			return 0
		last_activity_at = _ensure_aware_utc(thread.last_activity_at)
		if last_activity_at != observed_at:
			await schedule_thread_inactivity_maintenance(TypeID(thread.id), session)
			return 0
		needs_mandatory = thread_service.thread_needs_mandatory_maintenance(thread)
		needs_deferred = await thread_service.thread_needs_deferred_maintenance(
			thread,
			session,
		)
		if not needs_mandatory and not needs_deferred:
			return 0
		metadata: JSONObject = {"thread_id": str(thread.id)}
		if (
			await task_service.find_active_task(
				session, THREAD_MAINTENANCE_TASK, metadata
			)
			is not None
		):
			return 0
		principal = await load_principal_for_user(TypeID(thread.owner_id), session)
		await start_thread_inactivity_maintenance_task(session, principal, thread)
		return 1


# retroactive maintenance backfill --------------------------------------------
#
# the per-thread inactivity timer above never enqueues retroactive work. the
# functions below implement an explicit, off-by-default sweep that admins can
# enable to fill in maintenance for old threads with missing or stale
# metadata. all knobs come from `settings.tasks.maintenance_backfill`.


async def run_thread_maintenance_backfill_sweep(
	batch_size: int | None = None,
	max_lookback_days: int | None = None,
	min_inactivity_hours: int | None = None,
	respect_enabled: bool = True,
) -> JSONObject:
	"""dispatch maintenance for stale threads in one bounded batch.

	this function is the shared core for both the scheduled task and the
	manual admin trigger. callers control whether the master enabled flag
	is honored via `respect_enabled`; manual admin runs intentionally pass
	`respect_enabled=False` so an admin can spot-check the feature without
	leaving the schedule on.

	args:
		batch_size: override the configured batch size for this run.
		max_lookback_days: override the configured lookback window.
		min_inactivity_hours: override the configured minimum inactivity.
		respect_enabled: when True, returns immediately if the master
			toggle is off. set False for manual admin invocations.

	returns a JSON-friendly result describing how many threads were
	dispatched, how many were skipped because they already had an active
	maintenance task, and the parameters used.
	"""
	if respect_enabled:
		settings.reload()
	backfill_settings = settings.tasks.maintenance_backfill
	if respect_enabled and not backfill_settings.enabled:
		logger.info(
			"thread maintenance backfill sweep skipped reason=disabled "
			"respect_enabled=%s schedule_id=%s",
			respect_enabled,
			THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID,
		)
		return {"skipped": True, "reason": "disabled", "dispatched": 0}

	effective_batch = (
		batch_size if batch_size is not None else backfill_settings.batch_size
	)
	effective_lookback = (
		max_lookback_days
		if max_lookback_days is not None
		else backfill_settings.max_lookback_days
	)
	effective_inactivity = (
		min_inactivity_hours
		if min_inactivity_hours is not None
		else backfill_settings.min_inactivity_hours
	)
	if effective_batch <= 0 or effective_lookback <= 0 or effective_inactivity <= 0:
		logger.warning(
			"thread maintenance backfill sweep skipped reason=invalid_bounds "
			"batch_size=%d lookback_days=%d min_inactivity_hours=%d",
			effective_batch,
			effective_lookback,
			effective_inactivity,
		)
		return {
			"skipped": True,
			"reason": "invalid_bounds",
			"dispatched": 0,
		}

	now = datetime.now(tz=UTC)
	inactive_before = now - timedelta(hours=effective_inactivity)
	inactive_since = now - timedelta(days=effective_lookback)

	dispatched = 0
	skipped_existing = 0
	dispatched_thread_ids: list[JSONValue] = []
	async with async_session_local() as session:
		threads = await thread_service.list_threads_due_for_maintenance(
			session,
			inactive_before=inactive_before,
			inactive_since=inactive_since,
			limit=effective_batch,
		)
		for thread in threads:
			metadata: JSONObject = {"thread_id": str(thread.id)}
			existing = await task_service.find_active_task(
				session, THREAD_MAINTENANCE_TASK, metadata
			)
			if existing is not None:
				logger.info(
					"thread maintenance backfill skipped active task "
					"thread_id=%s task_id=%s",
					thread.id,
					existing.id,
				)
				skipped_existing += 1
				continue
			principal = await load_principal_for_user(TypeID(thread.owner_id), session)
			await start_thread_inactivity_maintenance_task(
				session,
				principal,
				thread,
				source="backfill_sweep",
				reason="backfill_sweep",
			)
			dispatched += 1
			dispatched_thread_ids.append(str(thread.id))

	logger.info(
		"thread maintenance backfill swept threads=%d"
		" dispatched=%d skipped_existing=%d",
		len(dispatched_thread_ids) + skipped_existing,
		dispatched,
		skipped_existing,
	)
	return {
		"dispatched": dispatched,
		"skipped_existing": skipped_existing,
		"batch_size": effective_batch,
		"max_lookback_days": effective_lookback,
		"min_inactivity_hours": effective_inactivity,
		"dispatched_thread_ids": dispatched_thread_ids,
	}


@broker.task(task_name=THREAD_MAINTENANCE_BACKFILL_TASK)
async def dispatch_thread_maintenance_backfill_sweep() -> JSONObject:
	"""scheduled entrypoint for the retroactive maintenance sweep.

	running this task is gated on `settings.tasks.maintenance_backfill.enabled`
	and its other knobs. when disabled it returns a `skipped` result so the
	tick does no work and spends no model tokens.
	"""
	return await run_thread_maintenance_backfill_sweep(respect_enabled=True)


async def reconcile_thread_maintenance_backfill_schedule() -> bool:
	"""install or remove the backfill cron schedule based on settings.

	called at API boot and again whenever the cache invalidation signal
	`thread_maintenance_backfill` fires. the function is idempotent: it
	always deletes the existing schedule first, then installs a new one
	when the feature is enabled. returns True if a schedule is currently
	installed after the reconcile, False otherwise.
	"""
	if boot_settings.TESTING:
		return False
	settings.reload()
	await redis_schedule_source.delete_schedule(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	backfill_settings = settings.tasks.maintenance_backfill
	if not backfill_settings.enabled:
		logger.info("thread maintenance backfill schedule cleared (disabled)")
		return False
	try:
		await (
			dispatch_thread_maintenance_backfill_sweep.kicker()
			.with_schedule_id(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
			.schedule_by_cron(redis_schedule_source, backfill_settings.cron)
		)
	except ValueError as exc:
		logger.warning(
			"thread maintenance backfill cron rejected by taskiq: %s (cron=%r)",
			exc,
			backfill_settings.cron,
		)
		return False
	logger.info(
		"thread maintenance backfill schedule installed"
		" cron=%r batch_size=%d lookback_days=%d",
		backfill_settings.cron,
		backfill_settings.batch_size,
		backfill_settings.max_lookback_days,
	)
	return True


async def clear_disabled_thread_maintenance_backfill_schedule() -> bool:
	"""remove any persisted backfill schedule before TaskIQ startup when disabled."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	backfill_settings = settings.tasks.maintenance_backfill
	if backfill_settings.enabled:
		return False
	await redis_schedule_source.delete_schedule(THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID)
	logger.info(
		"thread maintenance backfill schedule cleared before taskiq startup "
		"reason=disabled schedule_id=%s",
		THREAD_MAINTENANCE_BACKFILL_SCHEDULE_ID,
	)
	return True


def _on_backfill_settings_invalidation() -> None:
	"""react to a settings update by reconciling the backfill schedule.

	the cache invalidation pubsub handler is sync, so we hand the async
	reconcile off to the running event loop without blocking the listener.
	"""
	try:
		loop = asyncio.get_running_loop()
	except RuntimeError:
		logger.debug("backfill invalidation received outside an event loop; skipping")
		return
	loop.create_task(reconcile_thread_maintenance_backfill_schedule())


on_invalidation(
	THREAD_MAINTENANCE_BACKFILL_INVALIDATION_SIGNAL,
	_on_backfill_settings_invalidation,
)
