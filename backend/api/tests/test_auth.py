"""Tests covering the authentication flow."""

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User


@pytest.mark.asyncio
async def test_login_and_me_endpoint(client: AsyncClient) -> None:
	"""User can obtain a token and access /users/me."""
	user_payload = {
		"email": "auth-flow@example.com",
		"username": "auth-flow",
		"password": "passw0rd!",
	}
	create_resp = await client.post("/v1/users", json=user_payload)
	assert create_resp.status_code == 201

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	me_resp = await client.get(
		"/v1/users/me",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert me_resp.status_code == 200
	me_data = me_resp.json()
	assert me_data["email"] == user_payload["email"]
	assert me_data["username"] == user_payload["username"]


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
	"""Incorrect password should produce HTTP 400."""
	user_payload = {
		"email": "auth-fail@example.com",
		"username": "auth-fail",
		"password": "correct-password",
	}
	create_resp = await client.post("/v1/users", json=user_payload)
	assert create_resp.status_code == 201

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": "wrong"},
	)
	assert login_resp.status_code == 400
	assert login_resp.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_login_inactive_user_rejected(client: AsyncClient) -> None:
	"""Inactive users should not receive tokens."""
	user_payload = {
		"email": "inactive@example.com",
		"username": "inactive-user",
		"password": "correct-password",
		"is_active": False,
	}
	create_resp = await client.post("/v1/users", json=user_payload)
	assert create_resp.status_code == 201

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	assert login_resp.status_code == 400
	assert login_resp.json()["detail"] == "Inactive user"


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
	"""Login with non-existent user should fail."""
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": "nonexistent@example.com", "password": "password"},
	)
	assert login_resp.status_code == 400


@pytest.mark.asyncio
async def test_access_protected_endpoint_invalid_token(client: AsyncClient) -> None:
	"""Accessing protected endpoint with invalid token should fail."""
	resp = await client.get(
		"/v1/users/me",
		headers={"Authorization": "Bearer invalid-token"},
	)
	assert resp.status_code == 401


@pytest.mark.asyncio
async def test_access_protected_endpoint_user_deleted(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	"""Accessing protected endpoint with valid token but deleted user should fail."""
	# Create user
	user_payload = {
		"email": "deleted@example.com",
		"username": "deleted-user",
		"password": "password",
	}
	await client.post("/v1/users", json=user_payload)

	# Login
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	token = login_resp.json()["access_token"]

	# Delete user directly in DB
	await db_session.execute(delete(User).where(User.email == user_payload["email"]))
	await db_session.commit()

	# Try to access protected endpoint
	resp = await client.get(
		"/v1/users/me",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 401


@pytest.mark.asyncio
async def test_access_protected_endpoint_inactive_user(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	"""Inactive user cannot access protected endpoints even with valid token."""
	# Create user
	user_payload = {
		"email": "inactive-access@example.com",
		"username": "inactive-access",
		"password": "password",
		"is_active": True,
	}
	create_resp = await client.post("/v1/users", json=user_payload)
	user_id = create_resp.json()["id"]

	# Login to get token
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	token = login_resp.json()["access_token"]

	# Deactivate user directly in DB
	await db_session.execute(
		update(User).where(User.id == user_id).values(is_active=False)
	)
	await db_session.commit()

	# Try to access protected endpoint
	resp = await client.get(
		"/v1/users/me",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 400
	assert resp.json()["detail"] == "Inactive user"
