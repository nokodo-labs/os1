"""Tests covering the authentication flow."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.many_to_many import user_role_association
from api.models.role import Role
from api.models.user import User
from api.schemas.user import UserCreate
from api.settings import settings
from api.v1.service import auth as auth_service
from api.v1.service import users as user_service
from api.v1.service.auth import (
	Principal,
	get_current_active_user,
	get_current_principal,
)
from nokodo_ai.utils.security import create_jwt_token
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_login_and_fetch_user(client: AsyncClient) -> None:
	"""User can obtain a token and fetch their user resource via /users/{id}."""
	bootstrap_payload = {
		"email": "bootstrap-admin-auth-flow@example.com",
		"password": "passw0rd!",
		"is_superuser": True,
	}
	bootstrap_resp = await client.post("/v1/users", json=bootstrap_payload)
	assert bootstrap_resp.status_code == 201

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
	assert "nokodo:refresh_token=" in login_resp.headers.get("set-cookie", "")
	token = login_resp.json()["access_token"]
	refresh_cookie = login_resp.cookies.get("nokodo:refresh_token")
	assert refresh_cookie

	me_resp = await client.get(
		f"/v1/users/{user_id}",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert me_resp.status_code == 200
	me_data = me_resp.json()
	assert me_data["email"] == user_payload["email"]

	refresh_resp = await client.post(
		"/v1/auth/refresh",
		cookies={"nokodo:refresh_token": refresh_cookie},
		headers={"Origin": "http://localhost:888"},
	)
	assert refresh_resp.status_code == 200
	refresh_token = refresh_resp.json()["access_token"]
	assert refresh_token

	me_refreshed_resp = await client.get(
		f"/v1/users/{user_id}",
		headers={"Authorization": f"Bearer {refresh_token}"},
	)
	assert me_refreshed_resp.status_code == 200


@pytest.mark.asyncio
async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
	"""Incorrect password should produce HTTP 400."""
	bootstrap_payload = {
		"email": "bootstrap-admin-auth-fail@example.com",
		"password": "correct-password",
		"is_superuser": True,
	}
	bootstrap_resp = await client.post("/v1/users", json=bootstrap_payload)
	assert bootstrap_resp.status_code == 201

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
	assert login_resp.json()["detail"] == "incorrect email or password"


@pytest.mark.asyncio
async def test_login_inactive_user_rejected(client: AsyncClient) -> None:
	"""Inactive users should not receive tokens."""
	admin_payload = {
		"email": "admin-inactive@example.com",
		"password": "password",
		"is_superuser": True,
	}
	admin_resp = await client.post("/v1/users", json=admin_payload)
	assert admin_resp.status_code == 201

	admin_login = await client.post(
		"/v1/auth/login/access-token",
		data={
			"username": admin_payload["email"],
			"password": admin_payload["password"],
		},
	)
	assert admin_login.status_code == 200
	admin_token = admin_login.json()["access_token"]

	user_payload = {
		"email": "inactive@example.com",
		"password": "correct-password",
		"is_active": False,
	}
	create_resp = await client.post(
		"/v1/users",
		json=user_payload,
		headers={"Authorization": f"Bearer {admin_token}"},
	)
	assert create_resp.status_code == 201

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	assert login_resp.status_code == 400
	assert login_resp.json()["detail"] == "inactive user"


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
		is_superuser=True,
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
		is_superuser=True,
	)
	user = await user_service.create_user(user_in, db_session)

	# Generate token
	token = create_jwt_token(
		subject=user.id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
	)

	# Success
	current_user = await auth_service.get_current_user(token, db_session)
	assert current_user.id == user.id

	# Invalid token
	with pytest.raises(HTTPException):
		await auth_service.get_current_user("invalid_token", db_session)

	# User not found (deleted)
	missing_user_id = new_typeid("user")
	while missing_user_id == user.id:
		missing_user_id = new_typeid("user")
	token_deleted = create_jwt_token(
		subject=missing_user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
	)
	with pytest.raises(HTTPException):
		await auth_service.get_current_user(token_deleted, db_session)


@pytest.mark.asyncio
async def test_service_get_current_user_no_sub(db_session: AsyncSession) -> None:
	"""Test get_current_user with token missing sub claim."""
	from datetime import UTC, datetime

	from authlib.jose import jwt

	payload = {"exp": int(datetime.now(UTC).timestamp()) + 3600}
	headers = {"alg": settings.security.jwt_algorithm, "typ": "JWT"}
	token = jwt.encode(headers, payload, settings.security.secret_key)
	token_str = token.decode("utf-8") if isinstance(token, bytes) else token

	with pytest.raises(HTTPException):
		await auth_service.get_current_user(token_str, db_session)


@pytest.mark.asyncio
async def test_principal_permission_checks_and_active_guard(
	db_session: AsyncSession,
) -> None:
	"""Ensure Principal permission wildcards and active guard behave."""
	admin_seed = await user_service.create_user(
		UserCreate(
			email="principal-admin@example.com", password="pw", is_superuser=True
		),
		db_session,
	)
	user = await user_service.create_user(
		UserCreate(email="principal@example.com", password="pw"),
		db_session,
		actor=admin_seed,
	)
	principal = Principal(
		user=user,
		group_ids=(),
		permissions=frozenset({"foo:read", "bar:*"}),
	)
	assert principal.has_permission("foo:read")
	assert principal.has_permission("bar:write")
	assert not principal.has_permission("baz:read")

	admin = Principal(
		user=User(
			email="admin-perm@example.com",
			hashed_password="x",
			is_superuser=True,
			is_active=True,
		),
		group_ids=(),
		permissions=frozenset(),
	)
	assert admin.has_permission("anything")

	inactive = User(
		email="inactive@example.com",
		hashed_password="x",
		is_active=False,
		is_superuser=False,
	)
	with pytest.raises(HTTPException):
		await get_current_active_user(inactive)


def test_principal_permission_star() -> None:
	user = User(email="star@example.com", hashed_password="x", is_superuser=False)
	principal = Principal(user=user, group_ids=(), permissions=frozenset({"*"}))
	assert principal.has_permission("any:permission")
	admin = User(email="star-admin@example.com", hashed_password="x", is_superuser=True)
	assert Principal(user=admin, group_ids=(), permissions=frozenset()).is_admin


@pytest.mark.asyncio
async def test_optional_user_and_require_admin(db_session: AsyncSession) -> None:
	user = User(email="optional@example.com", hashed_password="x", is_active=True)
	db_session.add(user)
	await db_session.commit()

	assert await auth_service.get_optional_user(None, db_session) is None

	non_admin = Principal(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		await auth_service.require_admin(non_admin)


@pytest.mark.asyncio
async def test_get_current_active_user_allows_active_user(
	db_session: AsyncSession,
) -> None:
	user = User(email="active@example.com", hashed_password="pw", is_active=True)
	assert await get_current_active_user(user) is user


@pytest.mark.asyncio
async def test_get_current_principal_with_role(db_session: AsyncSession) -> None:
	role = Role(
		name="tester",
		default_permissions={
			"resource_access": {},
			"action_permissions": ["prompts:read"],
		},
	)
	user = User(
		email="principal-role@example.com", hashed_password="pw", is_active=True
	)
	db_session.add_all([role, user])
	await db_session.flush()
	# insert M2M association directly
	await db_session.execute(
		insert(user_role_association).values(user_id=user.id, role_id=role.id)
	)
	await db_session.commit()
	# re-load user with roles eagerly
	await db_session.refresh(user, attribute_names=["roles"])

	principal = await get_current_principal(user, db_session)
	assert "prompts:read" in principal.permissions
	assert principal.user_id == str(user.id)
