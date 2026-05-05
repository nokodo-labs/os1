import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq.brokers.inmemory_broker import InMemoryBroker
from taskiq.schedule_sources import LabelScheduleSource

from api.models.task import TaskStatus, TaskType
from api.schemas.task import TaskCreate, TaskListFilters, TaskUpdate
from api.schemas.user import UserCreate
from api.taskiq import broker
from api.v1.service import tasks as task_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from api.v1.tasks.threads import THREAD_INACTIVITY_SWEEP_TASK
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_create_task(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test creating a task."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	payload = {
		"user_id": user["id"],
		"task_type": "custom",
		"stage": "initialization",
	}
	response = await client.post("/v1/tasks", json=payload, headers=headers)
	assert response.status_code == 201
	data = response.json()
	assert data["user_id"] == user["id"]
	assert data["task_type"] == "custom"
	assert data["status"] == "running"
	assert "id" in data


@pytest.mark.asyncio
async def test_list_tasks(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test listing tasks."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	# Create a task first
	payload = {
		"user_id": user["id"],
		"task_type": "custom",
	}
	await client.post("/v1/tasks", json=payload, headers=headers)

	response = await client.get("/v1/tasks", headers=headers)
	assert response.status_code == 200
	data = response.json()
	assert len(data) >= 1
	assert data[0]["user_id"] == user["id"]


@pytest.mark.asyncio
async def test_list_tasks_sorting(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""List tasks supports server-side sort_by + sort_dir."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	resp_b = await client.post(
		"/v1/tasks",
		headers=headers,
		json={
			"user_id": user["id"],
			"task_type": "custom",
			"stage": "b",
		},
	)
	assert resp_b.status_code == 201
	resp_a = await client.post(
		"/v1/tasks",
		headers=headers,
		json={
			"user_id": user["id"],
			"task_type": "custom",
			"stage": "a",
		},
	)
	assert resp_a.status_code == 201

	response = await client.get(
		"/v1/tasks",
		headers=headers,
		params={"sort_by": "stage", "sort_dir": "asc", "limit": 50},
	)
	assert response.status_code == 200
	data = response.json()
	assert [t["stage"] for t in data[:2]] == ["a", "b"]


@pytest.mark.asyncio
async def test_list_tasks_filter(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test listing tasks with filters."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	# Create tasks with different statuses
	task1 = {
		"user_id": user["id"],
		"task_type": "custom",
	}
	task2 = {
		"user_id": user["id"],
		"task_type": "custom",
	}
	await client.post("/v1/tasks", json=task1, headers=headers)
	created_completed = await client.post("/v1/tasks", json=task2, headers=headers)
	await client.patch(
		f"/v1/tasks/{created_completed.json()['id']}",
		json={"status": "complete"},
		headers=headers,
	)

	# Filter by status
	response = await client.get(
		"/v1/tasks",
		params={"status_filter": "running"},
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert all(t["status"] == "running" for t in data)

	# Filter by user_id
	response = await client.get(
		"/v1/tasks",
		params={"user_id": user["id"]},
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert all(t["user_id"] == user["id"] for t in data)


@pytest.mark.asyncio
async def test_update_task(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test updating a task."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	# Create a task
	payload = {
		"user_id": user["id"],
		"task_type": "custom",
	}
	create_res = await client.post("/v1/tasks", json=payload, headers=headers)
	task_id = create_res.json()["id"]

	# Update the task
	update_payload = {"status": "running", "progress": 50}
	response = await client.patch(
		f"/v1/tasks/{task_id}",
		json=update_payload,
		headers=headers,
	)
	assert response.status_code == 200
	data = response.json()
	assert data["status"] == "running"
	assert data["progress"] == 50


@pytest.mark.asyncio
async def test_update_task_not_found(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test updating a non-existent task."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.patch(
		f"/v1/tasks/{new_typeid('task')}",
		json={"status": "complete"},
		headers=headers,
	)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_service_create_task(db_session: AsyncSession) -> None:
	"""Test creating a task directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_service@example.com",
		username="task_service",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		stage="init",
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)
	assert task.user_id == user.id
	assert task.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_start_task_executes_registered_runner_through_taskiq(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="taskiq_start@example.com",
			username="taskiq_start",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	runner_name = "tests.taskiq.execution"
	original_runners = dict(task_service._task_runners)
	in_memory_broker = InMemoryBroker(await_inplace=True)
	in_memory_entrypoint = in_memory_broker.task(
		task_name=task_service.execute_started_task_entrypoint.task_name
	)(task_service.execute_started_task_entrypoint.original_func)
	monkeypatch.setattr(
		task_service, "execute_started_task_entrypoint", in_memory_entrypoint
	)

	@task_service.register_task_runner(runner_name)
	async def _runner(ctx: task_service.TaskContext) -> JSONObject:
		await ctx.update(progress=55, stage="worked")
		return {"ok": True, "runtime": ctx.runtime.get("value")}

	await in_memory_broker.startup()
	try:
		task = await task_service.start_task(
			db_session,
			principal=principal,
			task_type=TaskType.CUSTOM,
			task_name=runner_name,
			runtime={"value": "from taskiq"},
		)
		await db_session.refresh(task)
		assert task.status == TaskStatus.COMPLETED
		assert task.progress == 100
		assert task.result == {"ok": True, "runtime": "from taskiq"}
	finally:
		await in_memory_broker.shutdown()
		task_service._task_runners.clear()
		task_service._task_runners.update(original_runners)


@pytest.mark.asyncio
async def test_task_registry_exposes_static_schedules() -> None:
	from api.tasks import registry as task_registry_module

	assert task_registry_module is not None

	source = LabelScheduleSource(broker)
	await source.startup()
	schedules = await source.get_schedules()
	task_names = {schedule.task_name for schedule in schedules}
	assert "reminders.dispatch_due_notifications" not in task_names
	assert "calendar.dispatch_due_notifications" not in task_names
	assert THREAD_INACTIVITY_SWEEP_TASK in task_names


@pytest.mark.asyncio
async def test_service_list_tasks(db_session: AsyncSession) -> None:
	"""Test listing tasks directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_list@example.com",
		username="task_list_test",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	# Create tasks
	for i in range(3):
		task_in = TaskCreate(
			user_id=user.id,
			task_type=TaskType.CUSTOM,
		)
		await task_service.create_task(task_in, db_session, principal=principal)

	tasks = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(user_id=user.id),
	)
	assert len(tasks) >= 3

	# Test filter
	tasks_pending = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(user_id=user.id, status_filter=TaskStatus.RUNNING),
	)
	assert len(tasks_pending) >= 3


@pytest.mark.asyncio
async def test_task_update_no_changes_does_not_touch_last_event(
	db_session: AsyncSession,
) -> None:
	"""No-op update should not set last_event_at and respects user scoping."""
	user_in = UserCreate(
		email="task_no_change@example.com",
		username="task_no_change",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	task = await task_service.create_task(
		TaskCreate(user_id=user.id, task_type=TaskType.CUSTOM),
		db_session,
		principal=principal,
	)
	last_event_at = task.last_event_at

	unchanged = await task_service.update_task(
		task.id,
		TaskUpdate(),
		db_session,
		principal=principal,
	)
	assert unchanged.last_event_at == last_event_at

	filtered = await task_service.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(status_filter=TaskStatus.RUNNING),
	)
	assert filtered


@pytest.mark.asyncio
async def test_service_update_task(db_session: AsyncSession) -> None:
	"""Test updating a task directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_update@example.com",
		username="task_update",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)

	# Update
	update_in = TaskUpdate(status=TaskStatus.COMPLETED)
	updated_task = await task_service.update_task(
		task.id,
		update_in,
		db_session,
		principal=principal,
	)
	assert updated_task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_service_get_task_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent task."""
	user = await user_service.create_user(
		UserCreate(
			email="task_nf@example.com",
			username="task_nf_test",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await task_service.update_task(
			"nonexistent",
			TaskUpdate(status=TaskStatus.COMPLETED),
			db_session,
			principal=principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_update_task_no_changes(db_session: AsyncSession) -> None:
	"""Test updating a task with no changes."""
	# Create user and task
	user_in = UserCreate(
		email="task_no_change@example.com",
		username="task_no_change",
		password="password123",
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
	)
	task = await task_service.create_task(task_in, db_session, principal=principal)

	# Update with no changes
	update_in = TaskUpdate()
	updated_task = await task_service.update_task(
		task.id,
		update_in,
		db_session,
		principal=principal,
	)
	assert updated_task.id == task.id
