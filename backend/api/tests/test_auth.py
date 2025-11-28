"""Tests covering the authentication flow."""

import pytest
from httpx import AsyncClient


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
