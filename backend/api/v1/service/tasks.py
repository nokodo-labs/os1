"""Service helpers and execution runtime for tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.database import async_session_local
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.task import Task, TaskStatus, TaskType
from api.schemas.task import Task as TaskSchema
from api.schemas.task import TaskCreate, TaskListFilters, TaskUpdate
from api.taskiq import broker
from api.v1.service import events as event_service
from api.v1.service import task_bus
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.listing import SortDir, apply_sort
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.sse import sse_encode
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

TASK_NAME_METADATA_KEY = "task_name"

_TERMINAL_STATUSES = {
	TaskStatus.COMPLETED,
	TaskStatus.FAILED,
	TaskStatus.CANCELLED,
}


class UnknownTaskError(Exception):
	"""Raised when a task stream cannot find the requested task."""

	def __init__(self, task_id: TypeID) -> None:
		super().__init__(str(task_id))
		self.task_id = task_id


class TaskCancelledError(Exception):
	"""Raised inside task runners after cancellation is requested."""


@dataclass(slots=True)
class TaskContext:
	"""Context passed to durable task runners."""

	task_id: TypeID
	user_id: TypeID
	metadata: JSONObject
	runtime: JSONObject

	async def update(
		self,
		progress: int | None = None,
		stage: str | None = None,
		result: JSONObject | None = None,
		metadata_update: JSONObject | None = None,
		data: JSONObject | None = None,
	) -> Task:
		"""update this task's visible execution state."""
		await self.check_cancelled()
		return await update_task_execution(
			self.task_id,
			progress=progress,
			stage=stage,
			result=result,
			metadata_update=metadata_update,
			event_type=EventType.TASK_UPDATED,
			data=data,
		)

	async def check_cancelled(self) -> None:
		"""raise TaskCancelled when the persisted task has been cancelled."""
		async with async_session_local() as session:
			task = await session.get(Task, self.task_id)
			if task is None:
				raise UnknownTaskError(self.task_id)
			if task.status == TaskStatus.CANCELLED:
				raise TaskCancelledError


type TaskRunner = Callable[[TaskContext], Awaitable[JSONObject | None]]
type TaskRunnerTimeout = int | float | Callable[[], int | float | None]

_task_runners: dict[str, TaskRunner] = {}
_task_runner_timeouts: dict[str, TaskRunnerTimeout] = {}


def register_task_runner(
	name: str,
	timeout_seconds: TaskRunnerTimeout | None = None,
) -> Callable[[TaskRunner], TaskRunner]:
	"""register a Task ORM runner by stable name."""
	if not name:
		raise ValueError("task runner name is required")
	if isinstance(timeout_seconds, (int, float)) and timeout_seconds <= 0:
		raise ValueError("task runner timeout must be positive")

	def _decorator(runner: TaskRunner) -> TaskRunner:
		if name in _task_runners:
			raise RuntimeError(f"task runner already registered: {name}")
		_task_runners[name] = runner
		if timeout_seconds is not None:
			_task_runner_timeouts[name] = timeout_seconds
		return runner

	return _decorator


def _resolve_task_runner_timeout(runner_name: str) -> float | None:
	timeout_config = _task_runner_timeouts.get(runner_name)
	if timeout_config is None:
		return None
	if isinstance(timeout_config, (int, float)):
		timeout: float | None = float(timeout_config)
	else:
		resolved = timeout_config()
		timeout = float(resolved) if resolved is not None else None
	if timeout is not None and timeout <= 0:
		raise ValueError("task runner timeout must be positive")
	return timeout


def _is_terminal(status_value: TaskStatus) -> bool:
	return status_value in _TERMINAL_STATUSES


def _task_event_payload(
	task: Task,
	event_type: EventType,
	data: JSONObject | None = None,
) -> dict[str, object]:
	return {
		"type": event_type.value,
		"task_id": str(task.id),
		"task": TaskSchema.model_validate(task).model_dump(mode="json", by_alias=True),
		"data": data or {},
	}


def _task_frame(
	task: Task,
	event_type: EventType,
	data: JSONObject | None = None,
) -> bytes:
	return sse_encode(
		event=event_type.value,
		data=_task_event_payload(task, event_type, data),
	)


async def _publish_task_event(
	session: AsyncSession,
	task: Task,
	event_type: EventType,
	data: JSONObject | None = None,
) -> None:
	await session.flush()
	await session.refresh(task)
	payload = _task_event_payload(task, event_type, data)
	event = Event(
		scope=EventScope.USER,
		scope_id=task.user_id,
		type=event_type,
		data=payload,
		user_id=task.user_id,
		task_id=task.id,
	)
	await event_service.persist_and_fanout_event(session, event=event)
	await task_bus.mirror_frame(TypeID(task.id), _task_frame(task, event_type, data))


def _event_type_for_status(status_value: TaskStatus) -> EventType:
	match status_value:
		case TaskStatus.RUNNING:
			return EventType.TASK_UPDATED
		case TaskStatus.COMPLETED:
			return EventType.TASK_COMPLETED
		case TaskStatus.FAILED:
			return EventType.TASK_FAILED
		case TaskStatus.CANCELLED:
			return EventType.TASK_CANCELLED
		case _:
			return EventType.TASK_UPDATED


def _runner_name(task: Task) -> str | None:
	metadata = task.metadata_ or {}
	value = metadata.get(TASK_NAME_METADATA_KEY)
	if isinstance(value, str) and value:
		return value
	return None


def _merge_metadata(task: Task, metadata_update: JSONObject | None) -> None:
	if metadata_update is None:
		return
	merged = dict(task.metadata_ or {})
	merged.update(metadata_update)
	task.metadata_ = merged


def _apply_public_update(task: Task, task_in: TaskUpdate) -> None:
	update_data = task_in.model_dump(exclude_unset=True, by_alias=True)
	for key, value in update_data.items():
		setattr(task, key, value)


def _apply_execution_update(
	task: Task,
	status_value: TaskStatus | None = None,
	progress: int | None = None,
	stage: str | None = None,
	result: JSONObject | None = None,
	metadata_update: JSONObject | None = None,
) -> None:
	if task.status == TaskStatus.CANCELLED and status_value != TaskStatus.CANCELLED:
		raise TaskCancelledError

	now = datetime.now(tz=UTC)
	if status_value is not None:
		task.status = status_value
		if status_value == TaskStatus.RUNNING and task.started_at is None:
			task.started_at = now
		elif status_value == TaskStatus.COMPLETED:
			task.completed_at = now
		elif status_value == TaskStatus.FAILED:
			task.completed_at = now
		elif status_value == TaskStatus.CANCELLED:
			task.cancelled_at = now
	if progress is not None:
		task.progress = max(0, min(100, progress))
	if stage is not None:
		task.stage = stage[:100]
	if result is not None:
		task.result = result
	_merge_metadata(task, metadata_update)
	task.last_event_at = now


async def get_task(task_id: str, session: AsyncSession, principal: Principal) -> Task:
	stmt = select(Task).where(Task.id == task_id)
	if not principal.is_admin:
		stmt = stmt.where(Task.user_id == principal.user.id)
	task = (await session.execute(stmt)).scalar_one_or_none()
	if task is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Task not found",
		)
	return task


async def create_task(
	task_in: TaskCreate,
	session: AsyncSession,
	principal: Principal,
) -> Task:
	require_permission(principal, "tasks:create")
	user_id = task_in.user_id if principal.is_admin else principal.user.id
	now = datetime.now(tz=UTC)
	task = Task(
		user_id=user_id,
		task_type=task_in.task_type,
		status=TaskStatus.RUNNING,
		progress=task_in.progress,
		stage=task_in.stage,
		result=task_in.result,
		spawned_thread_id=task_in.spawned_thread_id,
		started_at=now,
		last_event_at=now,
		metadata_=task_in.metadata,
	)
	session.add(task)
	await _publish_task_event(session, task, event_type=EventType.TASK_CREATED)
	await session.commit()
	await session.refresh(task)
	return task


async def start_task(
	session: AsyncSession,
	principal: Principal,
	task_type: TaskType,
	task_name: str,
	metadata: JSONObject | None = None,
	runtime: JSONObject | None = None,
	stage: str = "started",
	progress: int | None = 0,
	spawned_thread_id: TypeID | None = None,
	require_create_permission: bool = False,
) -> Task:
	"""start a Task row and enqueue its registered runner through TaskIQ."""
	if require_create_permission:
		require_permission(principal, "tasks:create")
	metadata_payload = dict(metadata or {})
	metadata_payload[TASK_NAME_METADATA_KEY] = task_name
	now = datetime.now(tz=UTC)
	task = Task(
		user_id=principal.user.id,
		task_type=task_type,
		status=TaskStatus.RUNNING,
		progress=progress,
		stage=stage,
		spawned_thread_id=spawned_thread_id,
		started_at=now,
		last_event_at=now,
		metadata_=metadata_payload,
	)
	session.add(task)
	await _publish_task_event(session, task, event_type=EventType.TASK_CREATED)
	await session.commit()
	await session.refresh(task)
	logger.info(
		"task created; enqueueing taskiq job task_id=%s task_name=%s user_id=%s",
		task.id,
		task_name,
		principal.user.id,
	)

	try:
		await enqueue_started_task(TypeID(task.id), runtime_payload=runtime or {})
	except Exception as exc:
		logger.exception("failed to enqueue task %s", task.id)
		await update_task_execution(
			TypeID(task.id),
			status_value=TaskStatus.FAILED,
			stage="failed to enqueue",
			result={"error": type(exc).__name__, "message": str(exc)[:500]},
		)
		raise HTTPException(
			status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
			detail="failed to enqueue task",
		) from exc
	logger.info(
		"taskiq job enqueued task_id=%s task_name=%s user_id=%s",
		task.id,
		task_name,
		principal.user.id,
	)

	return task


async def find_active_task(
	session: AsyncSession,
	task_name: str,
	metadata: JSONObject,
) -> Task | None:
	"""find an active Task row by runner name and string metadata fields."""
	stmt = select(Task).where(
		Task.status.in_((TaskStatus.PENDING, TaskStatus.RUNNING)),
		Task.metadata_[TASK_NAME_METADATA_KEY].as_string() == task_name,
	)
	for key, value in metadata.items():
		if isinstance(value, str):
			stmt = stmt.where(Task.metadata_[key].as_string() == value)
	return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def list_tasks(
	session: AsyncSession,
	principal: Principal,
	filters: TaskListFilters | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[Task]:
	task_filters = filters or TaskListFilters()
	stmt = select(Task)
	stmt = _apply_task_filters(stmt, task_filters, principal)

	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": Task.created_at,
			"updated_at": Task.updated_at,
			"status": Task.status,
			"task_type": Task.task_type,
			"stage": Task.stage,
			"last_event_at": Task.last_event_at,
		},
		tie_breaker=Task.id,
	)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def count_tasks(
	session: AsyncSession,
	principal: Principal,
	filters: TaskListFilters | None = None,
) -> int:
	"""count tasks matching the list filters."""
	task_filters = filters or TaskListFilters()
	stmt = _apply_task_filters(
		select(func.count()).select_from(Task),
		task_filters,
		principal,
	)
	return await session.scalar(stmt) or 0


def _apply_task_filters(
	stmt: Select,
	filters: TaskListFilters,
	principal: Principal,
) -> Select:
	"""apply task list filters."""
	if principal.is_admin:
		if filters.owner_id is not None:
			stmt = stmt.where(Task.user_id == filters.owner_id)
	else:
		if filters.owner_id is not None and filters.owner_id != principal.user.id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		stmt = stmt.where(Task.user_id == principal.user.id)
	if filters.spawned_thread_id is not None:
		stmt = stmt.where(Task.spawned_thread_id == str(filters.spawned_thread_id))
	if filters.status_filter is not None:
		stmt = stmt.where(Task.status == filters.status_filter)
	if filters.state_filter == "active":
		stmt = stmt.where(Task.status.in_((TaskStatus.PENDING, TaskStatus.RUNNING)))
	elif filters.state_filter == "ended":
		stmt = stmt.where(Task.status.in_(tuple(_TERMINAL_STATUSES)))
	return stmt


async def update_task(
	task_id: str,
	task_in: TaskUpdate,
	session: AsyncSession,
	principal: Principal,
) -> Task:
	task = await get_task(task_id, session, principal)
	if task_in.model_fields_set:
		_apply_public_update(task, task_in)
		task.last_event_at = datetime.now(tz=UTC)
		await _publish_task_event(session, task, event_type=EventType.TASK_UPDATED)
		await session.commit()
		await session.refresh(task)
	return task


async def update_task_execution(
	task_id: TypeID,
	status_value: TaskStatus | None = None,
	progress: int | None = None,
	stage: str | None = None,
	result: JSONObject | None = None,
	metadata_update: JSONObject | None = None,
	event_type: EventType | None = None,
	data: JSONObject | None = None,
) -> Task:
	"""update a task from runner code and publish its state."""
	async with async_session_local() as session:
		task = await session.get(Task, task_id)
		if task is None:
			raise UnknownTaskError(task_id)
		_apply_execution_update(
			task,
			status_value=status_value,
			progress=progress,
			stage=stage,
			result=result,
			metadata_update=metadata_update,
		)
		publish_type = event_type
		if publish_type is None:
			publish_type = (
				_event_type_for_status(status_value)
				if status_value is not None
				else EventType.TASK_UPDATED
			)
		await _publish_task_event(session, task, event_type=publish_type, data=data)
		await session.commit()
		await session.refresh(task)
		if _is_terminal(task.status):
			await task_bus.mark_task_end(TypeID(task.id))
		return task


async def fail_stale_active_tasks(
	task_names: Collection[str],
	stale_after: timedelta,
	reason: str,
) -> int:
	"""mark old active task rows failed so they cannot block new work forever."""
	if not task_names:
		return 0
	cutoff = datetime.now(tz=UTC) - stale_after
	async with async_session_local() as session:
		stmt = select(Task).where(
			Task.status.in_((TaskStatus.PENDING, TaskStatus.RUNNING)),
			Task.metadata_[TASK_NAME_METADATA_KEY].as_string().in_(tuple(task_names)),
			or_(
				Task.last_event_at <= cutoff,
				and_(Task.last_event_at.is_(None), Task.updated_at <= cutoff),
			),
		)
		result = await session.execute(stmt)
		stale_tasks = list(result.scalars().all())
		for task in stale_tasks:
			runner_name = _runner_name(task) or "unknown"
			last_event_at = task.last_event_at or task.updated_at or task.created_at
			_apply_execution_update(
				task,
				status_value=TaskStatus.FAILED,
				stage="stale task failed",
				result={
					"error": "stale_active_task",
					"message": reason,
					"task_name": runner_name,
					"last_event_at": last_event_at.isoformat()
					if last_event_at is not None
					else None,
				},
			)
			await _publish_task_event(
				session,
				task,
				event_type=EventType.TASK_FAILED,
			)
			await task_bus.mark_task_end(TypeID(task.id))
		return len(stale_tasks)


async def cancel_task(
	task_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	reason: str | None = None,
) -> Task:
	"""request cancellation for a task."""
	task = await get_task(task_id, session, principal)
	if _is_terminal(task.status):
		return task
	metadata_update: JSONObject = {
		"cancel_requested_at": datetime.now(tz=UTC).isoformat()
	}
	if reason:
		metadata_update["cancel_reason"] = reason
	_apply_execution_update(
		task,
		status_value=TaskStatus.CANCELLED,
		stage="cancelled",
		metadata_update=metadata_update,
	)
	await _publish_task_event(
		session,
		task,
		event_type=EventType.TASK_CANCELLED,
		data={"reason": reason} if reason else {},
	)
	await session.commit()
	await session.refresh(task)
	await task_bus.mark_task_end(TypeID(task.id))
	return task


async def execute_started_task(
	task_id: TypeID,
	runtime_payload: JSONObject | None = None,
) -> None:
	"""execute the registered runner for an already-started Task row."""
	async with async_session_local() as session:
		task = await session.get(Task, task_id)
		if task is None:
			raise UnknownTaskError(task_id)
		if _is_terminal(task.status):
			return
		runner_name = _runner_name(task)
		if runner_name is None:
			failure_message = f"task {task_id} has no registered runner name"
			await update_task_execution(
				task_id,
				status_value=TaskStatus.FAILED,
				stage="failed",
				result={"error": "RuntimeError", "message": failure_message},
			)
			raise RuntimeError(failure_message)
		runner = _task_runners.get(runner_name)
		if runner is None:
			failure_message = f"unknown task runner: {runner_name}"
			await update_task_execution(
				task_id,
				status_value=TaskStatus.FAILED,
				stage="failed",
				result={"error": "RuntimeError", "message": failure_message},
			)
			raise RuntimeError(failure_message)
		context = TaskContext(
			task_id=TypeID(task.id),
			user_id=TypeID(task.user_id),
			metadata=task.metadata_ or {},
			runtime=runtime_payload or {},
		)
		logger.info(
			"task execution started task_id=%s task_name=%s user_id=%s",
			task.id,
			runner_name,
			task.user_id,
		)

	try:
		timeout_seconds = _resolve_task_runner_timeout(runner_name)
		if timeout_seconds is None:
			result = await runner(context)
		else:
			async with asyncio.timeout(timeout_seconds):
				result = await runner(context)
		await context.check_cancelled()
		await update_task_execution(
			task_id,
			status_value=TaskStatus.COMPLETED,
			progress=100,
			stage="complete",
			result=result or {},
		)
		logger.info("task execution completed task_id=%s", task_id)
	except TaskCancelledError:
		await update_task_execution(
			task_id,
			status_value=TaskStatus.CANCELLED,
			stage="cancelled",
		)
		logger.info("task execution cancelled task_id=%s", task_id)
	except TimeoutError:
		logger.exception("task runner timed out: %s", task_id)
		await update_task_execution(
			task_id,
			status_value=TaskStatus.FAILED,
			stage="timed out",
			result={
				"error": "TimeoutError",
				"message": "task runner exceeded its timeout",
			},
		)
		raise
	except Exception as exc:
		logger.exception("task runner failed: %s", task_id)
		await update_task_execution(
			task_id,
			status_value=TaskStatus.FAILED,
			stage="failed",
			result={"error": type(exc).__name__, "message": str(exc)[:500]},
		)
		raise


@broker.task(task_name="tasks.execute")
async def execute_started_task_entrypoint(
	task_id: str,
	runtime_payload: JSONObject | None = None,
) -> None:
	"""TaskIQ entrypoint for persisted task executions."""
	await execute_started_task(TypeID(task_id), runtime_payload=runtime_payload)


async def enqueue_started_task(
	task_id: TypeID,
	runtime_payload: JSONObject | None = None,
) -> None:
	"""enqueue an already-started Task row through TaskIQ."""
	await execute_started_task_entrypoint.kiq(
		str(task_id), runtime_payload=runtime_payload or {}
	)


async def subscribe_task_stream(task_id: TypeID) -> AsyncGenerator[bytes]:
	"""subscribe to a task SSE stream with Redis catchup."""
	if await task_bus.task_log_known(task_id):
		async for frame in task_bus.subscribe_task_stream(task_id):
			yield frame
		yield sse_encode(event="done", data={})
		return

	async with async_session_local() as session:
		task = await session.get(Task, task_id)
		if task is None:
			raise UnknownTaskError(task_id)
		yield _task_frame(task, EventType.TASK_UPDATED)
		if _is_terminal(task.status):
			yield sse_encode(event="done", data={})
			return

	async for frame in task_bus.subscribe_task_stream(task_id):
		yield frame
	yield sse_encode(event="done", data={})
