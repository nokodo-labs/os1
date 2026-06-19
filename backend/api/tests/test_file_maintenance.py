"""tests for the retroactive file maintenance backfill sweep and endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq.schedule_sources import LabelScheduleSource

from api.boot_settings import boot_settings
from api.models.file import File, FileSource, FileStatus
from api.models.task import Task, TaskStatus, TaskType
from api.models.user import User
from api.schemas.user import UserCreate
from api.settings import settings
from api.taskiq import broker
from api.v1.service import tasks as task_service
from api.v1.service import users as user_service
from api.v1.service.files import (
	list_files_due_for_processing,
)
from api.v1.service.files.content_vectorization import (
	CONTENT_VECTOR_FINGERPRINT_KEY,
	_is_permanent_extraction_error,
)
from api.v1.tasks import files as file_tasks
from api.v1.tasks.files import (
	FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID,
	FILE_MAINTENANCE_BACKFILL_TASK,
	FILE_PROCESSING_TASK,
	clear_disabled_file_maintenance_backfill_schedule,
	run_file_maintenance_backfill_sweep,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID, new_typeid


class _FakeFileScheduleSource:
	def __init__(self) -> None:
		self.deleted: list[str] = []

	async def delete_schedule(self, schedule_id: str) -> None:
		self.deleted.append(schedule_id)


async def _create_user(db_session: AsyncSession, slug: str) -> User:
	return await user_service.create_user(
		UserCreate(
			email=f"{slug}@example.com",
			username=slug,
			password="password123",
			is_superuser=True,
		),
		db_session,
	)


async def _create_import_file(
	db_session: AsyncSession,
	owner_id: str,
	description: str | None = None,
	status: FileStatus = FileStatus.AVAILABLE,
	source: FileSource = FileSource.IMPORT,
	deleted: bool = False,
	metadata: JSONObject | None = None,
) -> File:
	file = File(
		id=TypeID(new_typeid("file")),
		owner_id=owner_id,
		source=source,
		storage_backend="local",
		storage_key=f"tests/{new_typeid('file')}",
		filename="imported.txt",
		mime_type="text/plain",
		size_bytes=10,
		checksum_sha256=None,
		description=description,
		status=status,
		metadata_=metadata,
	)
	if deleted:
		file.deleted_at = datetime.now(tz=UTC)
	db_session.add(file)
	await db_session.flush()
	return file


# list_files_due_for_processing


@pytest.mark.asyncio
async def test_list_files_due_for_processing_filters(
	db_session: AsyncSession,
) -> None:
	"""files missing a fingerprint or a description are due; fully done excluded."""
	user = await _create_user(db_session, "files_due_filter")
	owner_id = str(user.id)

	# due: missing both fingerprint and description.
	missing_both = await _create_import_file(db_session, owner_id)
	# due: has a description but never recorded a fingerprint.
	missing_fp = await _create_import_file(db_session, owner_id, description="done")
	# due: vectorized but never described.
	missing_desc = await _create_import_file(
		db_session, owner_id, metadata={CONTENT_VECTOR_FINGERPRINT_KEY: "fp"}
	)
	# due: pending files (e.g. stranded by a failed run) are picked back up.
	pending = await _create_import_file(db_session, owner_id, status=FileStatus.PENDING)
	# excluded: both a fingerprint and a description recorded.
	await _create_import_file(
		db_session,
		owner_id,
		description="done",
		metadata={CONTENT_VECTOR_FINGERPRINT_KEY: "fp"},
	)
	# excluded: soft deleted.
	await _create_import_file(db_session, owner_id, deleted=True)
	await db_session.commit()

	due = await list_files_due_for_processing(db_session, limit=10)

	assert {str(f.id) for f in due} == {
		str(missing_both.id),
		str(missing_fp.id),
		str(missing_desc.id),
		str(pending.id),
	}


# _is_permanent_extraction_error


def test_permanent_extraction_error_classification() -> None:
	"""4xx input errors and truncated-image text are permanent; 429/5xx retry."""

	class _StatusError(Exception):
		def __init__(self, status_code: int) -> None:
			super().__init__("boom")
			self.status_code = status_code

	assert _is_permanent_extraction_error(_StatusError(400)) is True
	assert _is_permanent_extraction_error(_StatusError(422)) is True
	assert _is_permanent_extraction_error(_StatusError(429)) is False
	assert _is_permanent_extraction_error(_StatusError(503)) is False
	assert _is_permanent_extraction_error(Exception("image file is truncated")) is True
	assert _is_permanent_extraction_error(Exception("temporary network blip")) is False


# run_file_maintenance_backfill_sweep


@pytest.mark.asyncio
async def test_file_maintenance_sweep_skipped_when_disabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""scheduled sweeps no-op while the master toggle is off."""
	monkeypatch.setenv("NOKODO__TASKS__FILE_MAINTENANCE__ENABLED", "false")
	result = await run_file_maintenance_backfill_sweep(respect_enabled=True)

	assert result["skipped"] is True
	assert result["reason"] == "disabled"
	assert result["dispatched"] == 0


@pytest.mark.asyncio
async def test_file_maintenance_sweep_dispatches_eligible_files(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""manual sweeps ignore the toggle and dispatch one task per due file."""
	user = await _create_user(db_session, "files_sweep_dispatch")
	owner_id = str(user.id)
	await _create_import_file(db_session, owner_id)
	await _create_import_file(db_session, owner_id)
	await db_session.commit()

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_file_maintenance_backfill_sweep(
		batch_size=5,
		respect_enabled=False,
	)

	# each due file gets exactly one unified processing task.
	assert result["dispatched"] == 2
	assert result["skipped_existing"] == 0
	assert result["batch_size"] == 5
	assert len(enqueued) == 2


@pytest.mark.asyncio
async def test_file_maintenance_sweep_skips_files_with_active_task(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""files already covered by an active task are not redispatched."""
	user = await _create_user(db_session, "files_sweep_skip")
	owner_id = str(user.id)
	# due file (missing both), but already has an active processing task.
	file = await _create_import_file(db_session, owner_id)

	now = datetime.now(tz=UTC)
	existing = Task(
		user_id=owner_id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued",
		started_at=now,
		last_event_at=now,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: FILE_PROCESSING_TASK,
			"file_id": str(file.id),
		},
	)
	db_session.add(existing)
	await db_session.commit()

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_file_maintenance_backfill_sweep(respect_enabled=False)

	assert result["dispatched"] == 0
	assert result["skipped_existing"] == 1
	assert enqueued == []


@pytest.mark.asyncio
async def test_file_maintenance_sweep_respects_batch_size(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the sweep dispatches no more than the configured batch size."""
	user = await _create_user(db_session, "files_sweep_batch")
	owner_id = str(user.id)
	for _ in range(3):
		await _create_import_file(db_session, owner_id)
	await db_session.commit()

	enqueued: list[str] = []

	async def _enqueue(task_id: TypeID, runtime_payload: JSONObject) -> None:
		_ = runtime_payload
		enqueued.append(str(task_id))

	monkeypatch.setattr(task_service, "enqueue_started_task", _enqueue)

	result = await run_file_maintenance_backfill_sweep(
		batch_size=2,
		respect_enabled=False,
	)

	assert result["dispatched"] == 2
	assert len(enqueued) == 2


# stale task reaping


@pytest.mark.asyncio
async def test_fail_stale_file_tasks_persists_failure(
	db_session: AsyncSession,
) -> None:
	"""a stale file processing task is committed as FAILED so its file is no
	longer skipped by the active-task guard forever."""
	user = await _create_user(db_session, "files_stale_reap")
	stale_after = timedelta(
		minutes=settings.tasks.file_maintenance.stale_task_cleanup_after_minutes
	)
	old = datetime.now(tz=UTC) - stale_after - timedelta(minutes=5)
	task = Task(
		user_id=str(user.id),
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="processing file",
		started_at=old,
		last_event_at=old,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: FILE_PROCESSING_TASK,
			"file_id": str(TypeID(new_typeid("file"))),
		},
	)
	db_session.add(task)
	await db_session.commit()
	task_id = task.id

	failed = await file_tasks.fail_stale_file_tasks()

	assert failed == 1
	db_session.expire_all()
	refreshed = (await db_session.scalars(select(Task).where(Task.id == task_id))).one()
	assert refreshed.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_removed_runner_fails_task_without_crash_loop(
	db_session: AsyncSession,
) -> None:
	"""a durable task whose runner was removed (e.g. a legacy file task carried
	over an upgrade) is marked FAILED instead of crash-looping, so its file can
	self-heal through the unified sweep."""
	user = await _create_user(db_session, "legacy_runner")
	now = datetime.now(tz=UTC)
	task = Task(
		user_id=str(user.id),
		task_type=TaskType.CUSTOM,
		status=TaskStatus.RUNNING,
		progress=0,
		stage="queued",
		started_at=now,
		last_event_at=now,
		metadata_={
			task_service.TASK_NAME_METADATA_KEY: "file.description",
			"file_id": str(TypeID(new_typeid("file"))),
		},
	)
	db_session.add(task)
	await db_session.commit()
	task_id = task.id

	with pytest.raises(RuntimeError, match="unknown task runner"):
		await task_service.execute_started_task(TypeID(task_id))

	db_session.expire_all()
	refreshed = (await db_session.scalars(select(Task).where(Task.id == task_id))).one()
	assert refreshed.status == TaskStatus.FAILED

	# a retry is a no-op because the task is already terminal: no crash loop.
	await task_service.execute_started_task(TypeID(task_id))


# schedule lifecycle


@pytest.mark.asyncio
async def test_disabled_file_maintenance_schedule_cleared_before_startup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""API boot clears a stale file maintenance schedule before TaskIQ startup."""
	monkeypatch.setattr(boot_settings, "TESTING", False)
	monkeypatch.setenv("NOKODO__TASKS__FILE_MAINTENANCE__ENABLED", "false")
	fake_source = _FakeFileScheduleSource()
	monkeypatch.setattr(file_tasks, "redis_schedule_source", fake_source)

	cleared = await clear_disabled_file_maintenance_backfill_schedule()

	assert cleared is True
	assert fake_source.deleted == [FILE_MAINTENANCE_BACKFILL_SCHEDULE_ID]


@pytest.mark.asyncio
async def test_file_maintenance_task_is_not_a_static_label_schedule() -> None:
	"""the sweep is installed dynamically, never as a fixed cron label.

	the schedule is reconciled at runtime via the redis schedule source so
	admins can toggle and tune it through Settings.
	"""
	source = LabelScheduleSource(broker)
	await source.startup()
	schedules = await source.get_schedules()
	task_names = {schedule.task_name for schedule in schedules}
	assert FILE_MAINTENANCE_BACKFILL_TASK not in task_names


# trigger endpoint


@pytest.mark.asyncio
async def test_file_maintenance_endpoint_requires_admin(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""non-admins cannot trigger the maintenance sweep."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.post(
		"/v1/files/maintenance-backfill/run",
		headers={str(k): str(v) for k, v in headers.items()},
	)

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_file_maintenance_endpoint_runs_for_admin(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""admins can spot-check the sweep regardless of the schedule toggle."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.post(
		"/v1/files/maintenance-backfill/run?batch_size=5",
		headers={str(k): str(v) for k, v in headers.items()},
	)

	assert response.status_code == 200
	data = response.json()
	assert data["dispatched"] == 0
	assert data["batch_size"] == 5
