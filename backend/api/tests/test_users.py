"""Tests for user endpoints."""

import pytest
from httpx import AsyncClient


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

	response = await client.post("/v1/users/", json=user_data)
	assert response.status_code == 201

	data = response.json()
	assert data["email"] == user_data["email"]
	assert data["username"] == user_data["username"]
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_get_users(client: AsyncClient) -> None:
	"""Test retrieving list of users."""
	response = await client.get("/v1/users/")
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
	create_response = await client.post("/v1/users/", json=user_data)
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
