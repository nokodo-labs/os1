"""file processing durable tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.models.task import Task, TaskType
from api.taskiq import broker, redis_schedule_source
from api.v1.service import tasks as task_service
from api.v1.service.auth import Principal, load_principal_for_user
from api.v1.service.files.processing import (
	process_file,
	process_file_content_vectorization,
	process_file_description,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


FILE_PROCESSING_TASK = "file.process"
FILE_CONTENT_VECTORIZATION_TASK = "file.content_vectorization"
FILE_DESCRIPTION_TASK = "file.description"
FILE_PROCESSING_DISPATCH_TASK = "file.processing.dispatch"
_FILE_RUNNER_TIMEOUT_SECONDS = 30 * 60


def _file_processing_schedule_id(file_id: TypeID) -> str:
	return f"file:processing:{file_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


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


async def start_file_content_vectorization_task(
	session: AsyncSession,
	principal: Principal,
	file_id: TypeID,
) -> Task:
	"""enqueue repeatable file content vectorization only."""
	metadata: JSONObject = {"file_id": str(file_id)}
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=FILE_CONTENT_VECTORIZATION_TASK,
		metadata=metadata,
		stage="queued content vectorization",
		progress=0,
	)


async def start_file_description_task(
	session: AsyncSession,
	principal: Principal,
	file_id: TypeID,
) -> Task:
	"""enqueue repeatable file description generation only."""
	metadata: JSONObject = {"file_id": str(file_id)}
	return await task_service.start_task(
		session,
		principal,
		task_type=TaskType.CUSTOM,
		task_name=FILE_DESCRIPTION_TASK,
		metadata=metadata,
		stage="queued file description",
		progress=0,
	)


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
	timeout_seconds=_FILE_RUNNER_TIMEOUT_SECONDS,
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


@task_service.register_task_runner(
	FILE_CONTENT_VECTORIZATION_TASK,
	timeout_seconds=_FILE_RUNNER_TIMEOUT_SECONDS,
)
async def run_file_content_vectorization_task(
	context: task_service.TaskContext,
) -> JSONObject:
	"""run only file content vectorization for a file."""
	file_id = _file_id_from_context(context)
	await context.update(progress=10, stage="vectorizing content")
	async with async_session_local() as session:
		result = await process_file_content_vectorization(file_id, session)
		await session.commit()
	await context.update(progress=90, stage="finalizing")
	return result


@task_service.register_task_runner(
	FILE_DESCRIPTION_TASK,
	timeout_seconds=_FILE_RUNNER_TIMEOUT_SECONDS,
)
async def run_file_description_task(context: task_service.TaskContext) -> JSONObject:
	"""run only file description generation for a file."""
	file_id = _file_id_from_context(context)
	await context.update(progress=10, stage="describing file")
	async with async_session_local() as session:
		result = await process_file_description(file_id, session)
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
