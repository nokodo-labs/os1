"""Tests covering the authentication flow."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.schemas.user import UserCreate
from api.v1.service import auth as auth_service
from api.v1.service import users as user_service
from nokodo_ai.utils.security import create_jwt_token


@pytest.mark.asyncio
async def test_login_and_fetch_user(client: AsyncClient) -> None:
	"""User can obtain a token and fetch their user resource via /users/{id}."""
	user_payload = {
		"email": "auth-flow@example.com",
		"password": "passw0rd!",
	}
	create_resp = await client.post("/v1/users", json=user_payload)
	assert create_resp.status_code == 201
	user_id = create_resp.json()["id"]

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	me_resp = await client.get(
		f"/v1/users/{user_id}",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert me_resp.status_code == 200
	me_data = me_resp.json()
	assert me_data["email"] == user_payload["email"]


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
	"""Incorrect password should produce HTTP 400."""
	user_payload = {
		"email": "auth-fail@example.com",
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
async def test_service_authenticate_user(db_session: AsyncSession) -> None:
	"""Test authenticate_user service directly."""
	# Create user
	user_in = UserCreate(
		email="auth_service@example.com",
		password="password123",
	)
	await user_service.create_user(user_in, db_session)

	# Success
	user = await auth_service.authenticate_user(
		db_session, "auth_service@example.com", "password123"
	)
	assert user is not None
	assert user.email == "auth_service@example.com"

	# Wrong password
	user = await auth_service.authenticate_user(
		db_session, "auth_service@example.com", "wrong"
	)
	assert user is None

	# User not found
	user = await auth_service.authenticate_user(
		db_session, "nonexistent@example.com", "password123"
	)
	assert user is None


@pytest.mark.asyncio
async def test_service_get_current_user(db_session: AsyncSession) -> None:
	"""Test get_current_user service directly."""
	# Create user
	user_in = UserCreate(
		email="current_user@example.com",
		username="current_user",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)

	# Generate token
	token = create_jwt_token(
		subject=user.id,
		secret_key=settings.SECRET_KEY,
		algorithm=settings.ALGORITHM,
	)

	# Success
	current_user = await auth_service.get_current_user(token, db_session)
	assert current_user.id == user.id

	# Invalid token
	with pytest.raises(HTTPException):
		await auth_service.get_current_user("invalid_token", db_session)

	# User not found (deleted)
	token_deleted = create_jwt_token(
		subject=99999,
		secret_key=settings.SECRET_KEY,
		algorithm=settings.ALGORITHM,
	)
	with pytest.raises(HTTPException):
		await auth_service.get_current_user(token_deleted, db_session)


@pytest.mark.asyncio
async def test_service_get_current_user_no_sub(db_session: AsyncSession) -> None:
	"""Test get_current_user with token missing sub claim."""
	from datetime import UTC, datetime

	from authlib.jose import jwt

	payload = {"exp": int(datetime.now(UTC).timestamp()) + 3600}
	headers = {"alg": settings.ALGORITHM, "typ": "JWT"}
	token = jwt.encode(headers, payload, settings.SECRET_KEY)
	token_str = token.decode("utf-8") if isinstance(token, bytes) else token

	with pytest.raises(HTTPException):
		await auth_service.get_current_user(token_str, db_session)
