import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
