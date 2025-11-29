"""Tests for user endpoints."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.user import UserCreate
from api.v1.service import users as user_service


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
	"""Test creating a new user."""
	user_data = {
		"email": "test@example.com",
		"username": "testuser",
		"password": "testpassword123",
		"is_active": True,
		"is_superuser": False,
	}

	response = await client.post("/v1/users", json=user_data)
	assert response.status_code == 201

	data = response.json()
	assert data["email"] == user_data["email"]
	assert data["username"] == user_data["username"]
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_get_users(client: AsyncClient) -> None:
	"""Test retrieving list of users."""
	response = await client.get("/v1/users")
	assert response.status_code == 200
	assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient) -> None:
	"""Test retrieving a specific user by ID."""
	# First create a user
	user_data = {
		"email": "test2@example.com",
		"username": "testuser2",
		"password": "testpassword123",
	}
	create_response = await client.post("/v1/users", json=user_data)
	assert create_response.status_code == 201
	user_id = create_response.json()["id"]

	# Then retrieve it
	response = await client.get(f"/v1/users/{user_id}")
	assert response.status_code == 200

	data = response.json()
	assert data["id"] == user_id
	assert data["email"] == user_data["email"]


@pytest.mark.asyncio
async def test_get_nonexistent_user(client: AsyncClient) -> None:
	"""Test retrieving a user that doesn't exist."""
	response = await client.get("/v1/users/99999")
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_user(client: AsyncClient) -> None:
	"""Test creating a user with an existing email."""
	user_data = {
		"email": "duplicate@example.com",
		"username": "duplicate",
		"password": "password",
	}
	# Create first user
	resp1 = await client.post("/v1/users", json=user_data)
	assert resp1.status_code == 201

	# Try to create duplicate
	resp2 = await client.post("/v1/users", json=user_data)
	assert resp2.status_code == 400
	assert resp2.json()["detail"] == "Email already registered"


@pytest.mark.asyncio
async def test_service_create_user(db_session: AsyncSession) -> None:
	"""Test creating a user directly via service."""
	user_in = UserCreate(
		email="service_test@example.com",
		username="service_test",
		password="password123",
		is_active=True,
		is_superuser=False,
	)
	user = await user_service.create_user(user_in, db_session)
	assert user.email == user_in.email
	assert user.username == user_in.username
	assert user.id is not None


@pytest.mark.asyncio
async def test_service_get_user(db_session: AsyncSession) -> None:
	"""Test getting a user directly via service."""
	# Create user first
	user_in = UserCreate(
		email="service_get@example.com",
		username="service_get",
		password="password123",
	)
	created_user = await user_service.create_user(user_in, db_session)

	# Get user
	fetched_user = await user_service.get_user(created_user.id, db_session)
	assert fetched_user.id == created_user.id
	assert fetched_user.email == created_user.email


@pytest.mark.asyncio
async def test_service_list_users(db_session: AsyncSession) -> None:
	"""Test listing users directly via service."""
	# Create a few users
	for i in range(3):
		user_in = UserCreate(
			email=f"list_{i}@example.com",
			username=f"list_{i}",
			password="password123",
		)
		await user_service.create_user(user_in, db_session)

	users = await user_service.list_users(db_session)
	assert len(users) >= 3


@pytest.mark.asyncio
async def test_service_get_user_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent user directly via service."""
	with pytest.raises(HTTPException) as exc:
		await user_service.get_user(99999, db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_create_duplicate_user(db_session: AsyncSession) -> None:
	"""Test creating a duplicate user directly via service."""
	user_in = UserCreate(
		email="duplicate_service@example.com",
		username="duplicate_service",
		password="password123",
	)
	await user_service.create_user(user_in, db_session)

	with pytest.raises(HTTPException) as exc:
		await user_service.create_user(user_in, db_session)
	assert exc.value.status_code == 400
