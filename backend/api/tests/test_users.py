"""Tests for user endpoints."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.user import UserCreate
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
	"""Test creating a new user."""
	bootstrap_admin = {
		"email": "admin@example.com",
		"password": "testpassword123",
		"is_superuser": True,
	}
	admin_resp = await client.post("/v1/users", json=bootstrap_admin)
	assert admin_resp.status_code == 201

	user_data = {
		"email": "test@example.com",
		"password": "testpassword123",
	}
	response = await client.post("/v1/users", json=user_data)
	assert response.status_code == 201

	data = response.json()
	assert data["email"] == user_data["email"]
	assert "id" in data
	assert "created_at" in data


@pytest.mark.asyncio
async def test_get_users(client: AsyncClient, admin_auth: dict[str, object]) -> None:
	"""Test retrieving list of users."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.get("/v1/users", headers=headers)
	assert response.status_code == 200
	assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_get_users_sorting(
	client: AsyncClient, admin_auth: dict[str, object]
) -> None:
	"""List users supports server-side sort_by + sort_dir."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	resp_a = await client.post(
		"/v1/users",
		json={"email": "a_sort@example.com", "password": "pw"},
		headers=headers,
	)
	assert resp_a.status_code == 201

	resp_b = await client.post(
		"/v1/users",
		json={"email": "b_sort@example.com", "password": "pw"},
		headers=headers,
	)
	assert resp_b.status_code == 201

	# Create a second pair in reverse order so the test catches missing sorting.
	resp_b2 = await client.post(
		"/v1/users",
		json={"email": "b_sort_2@example.com", "password": "pw"},
		headers=headers,
	)
	assert resp_b2.status_code == 201
	resp_a2 = await client.post(
		"/v1/users",
		json={"email": "a_sort_2@example.com", "password": "pw"},
		headers=headers,
	)
	assert resp_a2.status_code == 201

	response = await client.get(
		"/v1/users",
		headers=headers,
		params={"sort_by": "email", "sort_dir": "asc", "limit": 200},
	)
	assert response.status_code == 200
	emails = [u["email"] for u in response.json()]

	# Compare only the emails created in this test.
	created = {
		"a_sort@example.com",
		"b_sort@example.com",
		"a_sort_2@example.com",
		"b_sort_2@example.com",
	}
	filtered = [email for email in emails if email in created]
	assert filtered == [
		"a_sort@example.com",
		"a_sort_2@example.com",
		"b_sort@example.com",
		"b_sort_2@example.com",
	]


@pytest.mark.asyncio
async def test_get_user_by_id(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test retrieving a specific user by ID."""
	user = user_auth["user"]
	assert isinstance(user, dict)
	user_id = user["id"]

	# Then retrieve it
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.get(f"/v1/users/{user_id}", headers=headers)
	assert response.status_code == 200

	data = response.json()
	assert data["id"] == user_id
	assert data["email"] == user["email"]


@pytest.mark.asyncio
async def test_get_nonexistent_user(
	client: AsyncClient, admin_auth: dict[str, object]
) -> None:
	"""Test retrieving a user that doesn't exist."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.get(f"/v1/users/{new_typeid('user')}", headers=headers)
	assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_user(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Test creating a user with an existing email."""
	user_data = {
		"email": "duplicate@example.com",
		"password": "password",
	}
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	resp1 = await client.post("/v1/users", json=user_data, headers=headers)
	assert resp1.status_code == 201

	# Try to create duplicate
	resp2 = await client.post("/v1/users", json=user_data, headers=headers)
	assert resp2.status_code == 400
	assert resp2.json()["detail"] == "email already registered"


@pytest.mark.asyncio
async def test_service_create_user(db_session: AsyncSession) -> None:
	"""Test creating a user directly via service."""
	await user_service.create_user(
		UserCreate(
			email="bootstrap@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	user_in = UserCreate(
		email="service_test@example.com",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)
	assert user.email == user_in.email
	assert user.id is not None


@pytest.mark.asyncio
async def test_service_get_user(db_session: AsyncSession) -> None:
	"""Test getting a user directly via service."""
	# Create user first
	admin = await user_service.create_user(
		UserCreate(
			email="admin_get@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	user_in = UserCreate(email="service_get@example.com", password="password123")
	created_user = await user_service.create_user(
		user_in,
		db_session,
		actor=admin,
	)

	# Get user
	fetched_user = await user_service.get_user(
		created_user.id,
		db_session,
		principal=admin_principal,
	)
	assert fetched_user.id == created_user.id
	assert fetched_user.email == created_user.email


@pytest.mark.asyncio
async def test_service_list_users(db_session: AsyncSession) -> None:
	"""Test listing users directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_list@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	for i in range(2):
		user_in = UserCreate(email=f"list_{i}@example.com", password="password123")
		await user_service.create_user(user_in, db_session, actor=admin)

	users = await user_service.list_users(db_session, principal=admin_principal)
	assert len(users) >= 3


@pytest.mark.asyncio
async def test_service_get_user_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent user directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_nf@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await user_service.get_user(
			new_typeid("user"),
			db_session,
			principal=admin_principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_create_duplicate_user(db_session: AsyncSession) -> None:
	"""Test creating a duplicate user directly via service."""
	admin = await user_service.create_user(
		UserCreate(
			email="admin_dup@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	user_in = UserCreate(
		email="duplicate_service@example.com",
		password="password123",
	)
	await user_service.create_user(user_in, db_session, actor=admin)

	with pytest.raises(HTTPException) as exc:
		await user_service.create_user(user_in, db_session, actor=admin)
	assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_user_service_guards(db_session: AsyncSession) -> None:
	"""Non-admin principals should hit guardrails for list/get."""
	admin = await user_service.create_user(
		UserCreate(email="guard-admin@example.com", password="pw", is_superuser=True),
		db_session,
	)
	normal_user = await user_service.create_user(
		UserCreate(email="guard@example.com", password="pw"),
		db_session,
		actor=admin,
	)
	principal = Principal(user=normal_user, group_ids=(), permissions=frozenset())

	with pytest.raises(HTTPException):
		await user_service.list_users(db_session, principal=principal)

	with pytest.raises(HTTPException):
		await user_service.get_user(new_typeid("user"), db_session, principal=principal)


@pytest.mark.asyncio
async def test_unauthenticated_create_never_superuser(db_session: AsyncSession) -> None:
	"""Unauthenticated user creation should never produce a superuser."""
	# first user must request superuser explicitly
	with pytest.raises(HTTPException) as exc:
		await user_service.create_user(
			UserCreate(email="bootstrap-denied@example.com", password="pw"),
			db_session,
		)
	assert exc.value.status_code == 400
	assert isinstance(exc.value.detail, dict)
	assert exc.value.detail.get("code") == "bootstrap_required"
	assert "console_origin" in exc.value.detail

	bootstrap = await user_service.create_user(
		UserCreate(email="bootstrap@example.com", password="pw", is_superuser=True),
		db_session,
	)
	assert bootstrap.is_superuser is True
	assert bootstrap.is_active is True

	# unauthenticated create: even if is_superuser=True is passed,
	# result is a regular user
	sneaky = await user_service.create_user(
		UserCreate(email="sneaky@example.com", password="pw", is_superuser=True),
		db_session,
		actor=None,
	)
	assert sneaky.is_superuser is False
	assert sneaky.is_active is True

	# superuser can create another superuser
	new_admin = await user_service.create_user(
		UserCreate(email="new-admin@example.com", password="pw", is_superuser=True),
		db_session,
		actor=bootstrap,
	)
	assert new_admin.is_superuser is True
