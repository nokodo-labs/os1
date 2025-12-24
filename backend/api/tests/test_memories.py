"""Tests for memory service."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.memory import MemoryCreate
from api.schemas.user import UserCreate
from api.v1.service import memories as memory_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID, new_typeid


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
	principal = Principal(user=memory_user, group_ids=(), permissions=frozenset())
	memory_in = MemoryCreate(
		user_id=memory_user.id,
		content="Test memory content",
		category="test",
	)
	memory = await memory_service.create_memory(
		memory_in,
		db_session,
		principal=principal,
	)
	assert memory.content == "Test memory content"
	assert memory.user_id == memory_user.id


@pytest.mark.asyncio
async def test_list_memories(db_session: AsyncSession, memory_user) -> None:
	"""Test listing memories."""
	principal = Principal(user=memory_user, group_ids=(), permissions=frozenset())
	# Create memories
	for i in range(3):
		memory_in = MemoryCreate(
			user_id=memory_user.id,
			content=f"Memory {i}",
		)
		await memory_service.create_memory(memory_in, db_session, principal=principal)

	memories = await memory_service.list_memories(
		db_session,
		user_id=memory_user.id,
		principal=principal,
	)
	assert len(memories) >= 3


@pytest.mark.asyncio
async def test_get_memory(db_session: AsyncSession, memory_user) -> None:
	"""Test getting a memory."""
	principal = Principal(user=memory_user, group_ids=(), permissions=frozenset())
	memory_in = MemoryCreate(
		user_id=memory_user.id,
		content="Get memory test",
	)
	created = await memory_service.create_memory(
		memory_in,
		db_session,
		principal=principal,
	)

	fetched = await memory_service.get_memory(
		created.id,
		db_session,
		principal=principal,
	)
	assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_memory_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent memory."""
	user = await user_service.create_user(
		UserCreate(email="memory_nf@example.com", password="password123"),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await memory_service.get_memory(
			TypeID(new_typeid("mem")),
			db_session,
			principal=principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_memory_endpoint(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Hit GET /v1/memories/{id} to cover the router handler."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	user_id = user["id"]
	memory_resp = await client.post(
		"/v1/memories",
		json={"user_id": user_id, "content": "router"},
		headers=headers,
	)
	assert memory_resp.status_code == 201
	memory_id = memory_resp.json()["id"]

	fetched = await client.get(f"/v1/memories/{memory_id}", headers=headers)
	assert fetched.status_code == 200
	assert fetched.json()["id"] == memory_id


@pytest.mark.asyncio
async def test_admin_list_memories_for_other_user(db_session: AsyncSession) -> None:
	"""Admin principals can list memories for another user."""
	admin = await user_service.create_user(
		UserCreate(email="mem_admin@example.com", password="pw", is_superuser=True),
		db_session,
	)
	other = await user_service.create_user(
		UserCreate(email="mem_other@example.com", password="pw"),
		db_session,
		actor=admin,
	)
	principal = Principal(user=admin, group_ids=(), permissions=frozenset())
	memory = await memory_service.create_memory(
		MemoryCreate(user_id=other.id, content="c"),
		db_session,
		principal=principal,
	)
	listed = await memory_service.list_memories(
		db_session,
		principal=principal,
		user_id=TypeID(other.id),
	)
	assert listed and listed[0].id == memory.id


@pytest.mark.asyncio
async def test_non_admin_list_memories_forces_self(db_session: AsyncSession) -> None:
	"""Non-admin list_memories should ignore requested user_id."""
	admin = await user_service.create_user(
		UserCreate(
			email="mem_guard_admin@example.com", password="pw", is_superuser=True
		),
		db_session,
	)
	owner = await user_service.create_user(
		UserCreate(email="mem_guard_owner@example.com", password="pw"),
		db_session,
		actor=admin,
	)
	other = await user_service.create_user(
		UserCreate(email="mem_guard_other@example.com", password="pw"),
		db_session,
		actor=admin,
	)
	principal = Principal(user=owner, group_ids=(), permissions=frozenset())

	await memory_service.create_memory(
		MemoryCreate(user_id=owner.id, content="owner-memory"),
		db_session,
		principal=principal,
	)

	memories = await memory_service.list_memories(
		db_session,
		principal=principal,
		user_id=TypeID(other.id),
	)
	assert memories and all(mem.user_id == owner.id for mem in memories)
