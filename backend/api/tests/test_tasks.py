import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.task import TaskStatus, TaskType
from api.schemas.task import TaskCreate, TaskUpdate
from api.schemas.user import UserCreate
from api.v1.service import tasks as task_service
from api.v1.service import users as user_service


@pytest.mark.asyncio
async def test_create_task(
	client: AsyncClient,
	db_session: AsyncSession,
	test_user: dict,
) -> None:
	"""Test creating a task."""
	payload = {
		"user_id": test_user["id"],
		"task_type": "custom",
		"status": "pending",
		"stage": "initialization",
	}
	response = await client.post("/v1/tasks", json=payload)
	assert response.status_code == 201
	data = response.json()
	assert data["user_id"] == test_user["id"]
	assert data["task_type"] == "custom"
	assert data["status"] == "pending"
	assert "id" in data


@pytest.mark.asyncio
async def test_list_tasks(
	client: AsyncClient,
	db_session: AsyncSession,
	test_user: dict,
) -> None:
	"""Test listing tasks."""
	# Create a task first
	payload = {
		"user_id": test_user["id"],
		"task_type": "custom",
		"status": "pending",
	}
	await client.post("/v1/tasks", json=payload)

	response = await client.get("/v1/tasks")
	assert response.status_code == 200
	data = response.json()
	assert len(data) >= 1
	assert data[0]["user_id"] == test_user["id"]


@pytest.mark.asyncio
async def test_list_tasks_filter(
	client: AsyncClient,
	db_session: AsyncSession,
	test_user: dict,
) -> None:
	"""Test listing tasks with filters."""
	# Create tasks with different statuses
	task1 = {
		"user_id": test_user["id"],
		"task_type": "custom",
		"status": "pending",
	}
	task2 = {
		"user_id": test_user["id"],
		"task_type": "custom",
		"status": "complete",
	}
	await client.post("/v1/tasks", json=task1)
	await client.post("/v1/tasks", json=task2)

	# Filter by status
	response = await client.get("/v1/tasks", params={"status_filter": "pending"})
	assert response.status_code == 200
	data = response.json()
	assert all(t["status"] == "pending" for t in data)

	# Filter by user_id
	response = await client.get("/v1/tasks", params={"user_id": test_user["id"]})
	assert response.status_code == 200
	data = response.json()
	assert all(t["user_id"] == test_user["id"] for t in data)


@pytest.mark.asyncio
async def test_update_task(
	client: AsyncClient,
	db_session: AsyncSession,
	test_user: dict,
) -> None:
	"""Test updating a task."""
	# Create a task
	payload = {
		"user_id": test_user["id"],
		"task_type": "custom",
		"status": "pending",
	}
	create_res = await client.post("/v1/tasks", json=payload)
	task_id = create_res.json()["id"]

	# Update the task
	update_payload = {"status": "running", "progress": 50}
	response = await client.patch(f"/v1/tasks/{task_id}", json=update_payload)
	assert response.status_code == 200
	data = response.json()
	assert data["status"] == "running"
	assert data["progress"] == 50


@pytest.mark.asyncio
async def test_update_task_not_found(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Test updating a non-existent task."""
	response = await client.patch(
		"/v1/tasks/00000000-0000-0000-0000-000000000000",
		json={"status": "complete"},
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
	)
	user = await user_service.create_user(user_in, db_session)

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.PENDING,
		stage="init",
	)
	task = await task_service.create_task(task_in, db_session)
	assert task.user_id == user.id
	assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_service_list_tasks(db_session: AsyncSession) -> None:
	"""Test listing tasks directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_list@example.com",
		username="task_list",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)

	# Create tasks
	for i in range(3):
		task_in = TaskCreate(
			user_id=user.id,
			task_type=TaskType.CUSTOM,
			status=TaskStatus.PENDING,
		)
		await task_service.create_task(task_in, db_session)

	tasks = await task_service.list_tasks(db_session, user_id=user.id)
	assert len(tasks) >= 3

	# Test filter
	tasks_pending = await task_service.list_tasks(
		db_session, user_id=user.id, status_filter=TaskStatus.PENDING
	)
	assert len(tasks_pending) >= 3


@pytest.mark.asyncio
async def test_service_update_task(db_session: AsyncSession) -> None:
	"""Test updating a task directly via service."""
	# Create user
	user_in = UserCreate(
		email="task_update@example.com",
		username="task_update",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)

	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.PENDING,
	)
	task = await task_service.create_task(task_in, db_session)

	# Update
	update_in = TaskUpdate(status=TaskStatus.COMPLETED)
	updated_task = await task_service.update_task(task.id, update_in, db_session)
	assert updated_task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_service_get_task_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent task."""
	with pytest.raises(HTTPException) as exc:
		await task_service.update_task(
			"nonexistent", TaskUpdate(status=TaskStatus.COMPLETED), db_session
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
	)
	user = await user_service.create_user(user_in, db_session)
	task_in = TaskCreate(
		user_id=user.id,
		task_type=TaskType.CUSTOM,
		status=TaskStatus.PENDING,
	)
	task = await task_service.create_task(task_in, db_session)

	# Update with no changes
	update_in = TaskUpdate()
	updated_task = await task_service.update_task(task.id, update_in, db_session)
	assert updated_task.id == task.id
