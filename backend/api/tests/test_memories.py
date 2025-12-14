"""Tests for memory service."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.memory import MemoryCreate
from api.schemas.user import UserCreate
from api.v1.service import memories as memory_service
from api.v1.service import users as user_service


@pytest.fixture
async def memory_user(db_session: AsyncSession):
	"""Create a user for memory tests."""
	user_in = UserCreate(
		email="memory_test@example.com",
		password="password123",
	)
	return await user_service.create_user(user_in, db_session)


@pytest.mark.asyncio
async def test_create_memory(db_session: AsyncSession, memory_user) -> None:
	"""Test creating a memory."""
	memory_in = MemoryCreate(
		user_id=memory_user.id,
		content="Test memory content",
		category="test",
	)
	memory = await memory_service.create_memory(memory_in, db_session)
	assert memory.content == "Test memory content"
	assert memory.user_id == memory_user.id


@pytest.mark.asyncio
async def test_list_memories(db_session: AsyncSession, memory_user) -> None:
	"""Test listing memories."""
	# Create memories
	for i in range(3):
		memory_in = MemoryCreate(
			user_id=memory_user.id,
			content=f"Memory {i}",
		)
		await memory_service.create_memory(memory_in, db_session)

	memories = await memory_service.list_memories(db_session, user_id=memory_user.id)
	assert len(memories) >= 3


@pytest.mark.asyncio
async def test_get_memory(db_session: AsyncSession, memory_user) -> None:
	"""Test getting a memory."""
	memory_in = MemoryCreate(
		user_id=memory_user.id,
		content="Get memory test",
	)
	created = await memory_service.create_memory(memory_in, db_session)

	fetched = await memory_service.get_memory(created.id, db_session)
	assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_memory_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent memory."""
	with pytest.raises(HTTPException) as exc:
		await memory_service.get_memory("nonexistent", db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_memory_endpoint(client: AsyncClient) -> None:
	"""Hit GET /v1/memories/{id} to cover the router handler."""
	user_resp = await client.post(
		"/v1/users",
		json={
			"email": "memory-router@example.com",
			"username": "memory-router",
			"password": "password123",
		},
	)
	user_id = user_resp.json()["id"]
	memory_resp = await client.post(
		"/v1/memories",
		json={"user_id": user_id, "content": "router"},
	)
	assert memory_resp.status_code == 201
	memory_id = memory_resp.json()["id"]

	fetched = await client.get(f"/v1/memories/{memory_id}")
	assert fetched.status_code == 200
	assert fetched.json()["id"] == memory_id
