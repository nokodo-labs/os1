"""Tests for server-side login sessions: rotation, revocation, and reuse detection."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.event_types import EventType
from api.models.user_client import UserClient
from api.models.user_session import UserSession


ALLOWED_ORIGIN = "http://localhost:888"
REFRESH_COOKIE = "nokodo:refresh_token"


def auth_headers(auth: dict[str, object]) -> dict[str, str]:
	"""extract typed auth headers from an auth fixture payload."""
	headers = auth["headers"]
	assert isinstance(headers, dict)
	return {str(k): str(v) for k, v in headers.items()}


def auth_user(auth: dict[str, object]) -> dict[str, object]:
	"""extract the typed user dict from an auth fixture payload."""
	user = auth["user"]
	assert isinstance(user, dict)
	return {str(k): v for k, v in user.items()}


async def login(
	client: AsyncClient,
	email: str,
	password: str,
	client_key: str | None = None,
) -> tuple[str, str]:
	"""log in and return (access_token, refresh_cookie)."""
	headers = {"X-Client-Key": client_key} if client_key else {}
	resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
		headers=headers,
	)
	assert resp.status_code == 200
	refresh_cookie = resp.cookies.get(REFRESH_COOKIE)
	assert refresh_cookie
	return resp.json()["access_token"], refresh_cookie


async def refresh(client: AsyncClient, refresh_cookie: str) -> tuple[int, str | None]:
	"""call refresh with an explicit cookie; return (status, new_cookie)."""
	client.cookies.set(REFRESH_COOKIE, refresh_cookie)
	resp = await client.post("/v1/auth/refresh", headers={"Origin": ALLOWED_ORIGIN})
	new_cookie = resp.cookies.get(REFRESH_COOKIE)
	client.cookies.delete(REFRESH_COOKIE)
	return resp.status_code, new_cookie


@pytest.mark.asyncio
async def test_login_creates_session_row(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	user = auth_user(user_auth)
	result = await db_session.execute(
		select(UserSession).where(UserSession.user_id == str(user["id"]))
	)
	sessions = list(result.scalars().all())
	assert len(sessions) >= 1
	assert all(s.revoked_at is None for s in sessions)
	assert all(s.expires_at > datetime.now(UTC) for s in sessions)


@pytest.mark.asyncio
async def test_refresh_rotates_and_old_token_dies_after_grace(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	_, first_cookie = await login(client, email, password)

	status1, second_cookie = await refresh(client, first_cookie)
	assert status1 == 200
	assert second_cookie and second_cookie != first_cookie

	# within the grace window the rotated-out token still converges
	status2, grace_cookie = await refresh(client, first_cookie)
	assert status2 == 200
	assert grace_cookie

	# push the rotation outside the grace window: the old token is now a replay
	user = auth_user(user_auth)
	result = await db_session.execute(
		select(UserSession)
		.where(UserSession.user_id == str(user["id"]))
		.order_by(UserSession.created_at.desc())
	)
	row = result.scalars().first()
	assert row is not None
	row.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
	db_session.add(row)
	await db_session.commit()

	status3, _ = await refresh(client, first_cookie)
	assert status3 == 401

	# reuse detection revoked the whole session: the current token dies too
	status4, _ = await refresh(client, second_cookie)
	assert status4 == 401


@pytest.mark.asyncio
async def test_refresh_rejects_pre_session_token(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""tokens minted before the session store (no sid/jti) force re-login."""
	from api.settings import settings
	from nokodo_ai.utils.security import create_jwt_token

	user = auth_user(user_auth)
	legacy = create_jwt_token(
		subject=str(user["id"]),
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		expires_delta=timedelta(days=1),
		additional_claims={"typ": "refresh"},
	)
	status, _ = await refresh(client, legacy)
	assert status == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	_, cookie = await login(client, email, password)

	client.cookies.set(REFRESH_COOKIE, cookie)
	logout_resp = await client.post(
		"/v1/auth/logout", headers={"Origin": ALLOWED_ORIGIN}
	)
	assert logout_resp.status_code == 204
	client.cookies.delete(REFRESH_COOKIE)

	status, _ = await refresh(client, cookie)
	assert status == 401


@pytest.mark.asyncio
async def test_sessions_are_independent(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""logging out one session must not touch the user's other sessions."""
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	_, cookie_a = await login(client, email, password)
	_, cookie_b = await login(client, email, password)

	client.cookies.set(REFRESH_COOKIE, cookie_a)
	logout_resp = await client.post(
		"/v1/auth/logout", headers={"Origin": ALLOWED_ORIGIN}
	)
	assert logout_resp.status_code == 204
	client.cookies.delete(REFRESH_COOKIE)

	status_a, _ = await refresh(client, cookie_a)
	status_b, _ = await refresh(client, cookie_b)
	assert status_a == 401
	assert status_b == 200


@pytest.mark.asyncio
async def test_revoke_sessions_endpoint(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	_, cookie_a = await login(client, email, password)
	_, cookie_b = await login(client, email, password)

	resp = await client.post(
		f"/v1/users/{user['id']}/sessions/revoke",
		headers=auth_headers(user_auth),
	)
	assert resp.status_code == 200
	assert resp.json() >= 2

	status_a, _ = await refresh(client, cookie_a)
	status_b, _ = await refresh(client, cookie_b)
	assert status_a == 401
	assert status_b == 401

	result = await db_session.execute(
		select(Event).where(
			Event.type == EventType.USER_SESSIONS_REVOKED,
			Event.user_id == str(user["id"]),
		)
	)
	assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_revoke_sessions_forbidden_for_other_user(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	admin = auth_user(admin_auth)
	resp = await client.post(
		f"/v1/users/{admin['id']}/sessions/revoke",
		headers=auth_headers(user_auth),
	)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_revokes_other_user_sessions(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	target = auth_user(user_auth)
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	_, cookie = await login(client, email, password)

	resp = await client.post(
		f"/v1/users/{target['id']}/sessions/revoke",
		headers=auth_headers(admin_auth),
	)
	assert resp.status_code == 200

	status, _ = await refresh(client, cookie)
	assert status == 401


@pytest.mark.asyncio
async def test_list_sessions_includes_history_without_token_state(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""session history exposes audit fields without either refresh jti."""
	user = auth_user(user_auth)
	row = UserSession(
		user_id=str(user["id"]),
		current_jti=f"history-{uuid4().hex}",
		expires_at=datetime.now(UTC) + timedelta(days=1),
		revoked_at=datetime.now(UTC),
	)
	db_session.add(row)
	await db_session.commit()
	row_id = str(row.id)

	response = await client.get(
		f"/v1/users/{user['id']}/sessions",
		headers=auth_headers(user_auth),
	)

	assert response.status_code == 200
	sessions = response.json()
	listed = next(item for item in sessions if item["id"] == row_id)
	assert listed["revoked_at"] is not None
	assert listed["is_active"] is False
	assert "current_jti" not in listed
	assert "prev_jti" not in listed


@pytest.mark.asyncio
async def test_list_sessions_forbidden_for_other_user(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	admin = auth_user(admin_auth)
	response = await client.get(
		f"/v1/users/{admin['id']}/sessions",
		headers=auth_headers(user_auth),
	)

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_lists_other_user_sessions(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	target = auth_user(user_auth)
	response = await client.get(
		f"/v1/users/{target['id']}/sessions",
		headers=auth_headers(admin_auth),
	)

	assert response.status_code == 200
	assert response.json()


@pytest.mark.asyncio
async def test_revoke_one_session_leaves_other_session_active(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	await login(client, email, password)
	await login(client, email, password)

	result = await db_session.execute(
		select(UserSession)
		.where(
			UserSession.user_id == str(user["id"]),
			UserSession.revoked_at.is_(None),
		)
		.order_by(UserSession.created_at.desc())
	)
	rows = list(result.scalars().all())
	assert len(rows) >= 2
	target, survivor = rows[:2]
	target_id = target.id
	survivor_id = survivor.id

	response = await client.post(
		f"/v1/users/{user['id']}/sessions/{target_id}/revoke",
		headers=auth_headers(user_auth),
	)

	assert response.status_code == 200
	assert response.json()["id"] == str(target_id)
	assert response.json()["is_active"] is False
	db_session.expire_all()
	refreshed = await db_session.execute(
		select(UserSession).where(UserSession.id.in_([target_id, survivor_id]))
	)
	by_id = {str(row.id): row for row in refreshed.scalars().all()}
	assert by_id[str(target_id)].revoked_at is not None
	assert by_id[str(survivor_id)].revoked_at is None


@pytest.mark.asyncio
async def test_revoke_one_session_rejects_wrong_user_path(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	admin = auth_user(admin_auth)
	target_user = auth_user(user_auth)
	result = await db_session.execute(
		select(UserSession).where(UserSession.user_id == str(target_user["id"]))
	)
	row = result.scalars().first()
	assert row is not None

	response = await client.post(
		f"/v1/users/{admin['id']}/sessions/{row.id}/revoke",
		headers=auth_headers(admin_auth),
	)

	assert response.status_code == 404


@pytest.mark.asyncio
async def test_password_change_revokes_sessions_and_emits_event(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	_, cookie = await login(client, email, password)

	resp = await client.post(
		f"/v1/users/{user['id']}/change-password",
		headers=auth_headers(user_auth),
		json={"current_password": password, "new_password": "rotated-pass-123"},
	)
	assert resp.status_code == 204

	status, _ = await refresh(client, cookie)
	assert status == 401

	result = await db_session.execute(
		select(Event).where(
			Event.type == EventType.USER_PASSWORD_CHANGED,
			Event.user_id == str(user["id"]),
		)
	)
	event = result.scalars().first()
	assert event is not None
	assert event.data["self_service"] is True


@pytest.mark.asyncio
async def test_email_change_emits_event(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	target = auth_user(user_auth)
	old_email = user_auth["email"]
	assert isinstance(old_email, str)
	new_email = f"evt-{uuid4().hex[:10]}@example.com"

	resp = await client.post(
		f"/v1/users/{target['id']}/change-email",
		headers=auth_headers(admin_auth),
		json={"new_email": new_email},
	)
	assert resp.status_code == 200

	result = await db_session.execute(
		select(Event).where(
			Event.type == EventType.USER_EMAIL_CHANGED,
			Event.user_id == str(target["id"]),
		)
	)
	event = result.scalars().first()
	assert event is not None
	assert event.data["old_email"] == old_email
	assert event.data["new_email"] == new_email
	assert event.data["self_service"] is False


@pytest.mark.asyncio
async def test_login_with_client_key_links_session(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""a client key at login spawns/links a user client on the session."""
	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	client_key = f"test-client-{uuid4().hex[:10]}"

	await login(client, email, password, client_key=client_key)

	client_result = await db_session.execute(
		select(UserClient).where(
			UserClient.user_id == str(user["id"]),
			UserClient.client_key == client_key,
		)
	)
	client_row = client_result.scalar_one_or_none()
	assert client_row is not None

	session_result = await db_session.execute(
		select(UserSession).where(UserSession.client_id == str(client_row.id))
	)
	assert session_result.scalars().first() is not None


@pytest.mark.asyncio
async def test_advance_session_cas_converges_losers(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""a CAS-losing refresh converges on the winner's jti instead of failing."""
	from api.v1.service.authentication import sessions as session_service

	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	await login(client, email, password)

	result = await db_session.execute(
		select(UserSession)
		.where(UserSession.user_id == str(user["id"]))
		.order_by(UserSession.created_at.desc())
	)
	row = result.scalars().first()
	assert row is not None
	presented = row.current_jti

	winner_jti = await session_service.advance_session(db_session, row, presented)
	assert winner_jti is not None and winner_jti != presented

	# simulate the losing worker: same presented jti, post-rotation row state
	await db_session.refresh(row)
	loser_jti = await session_service.advance_session(db_session, row, presented)
	assert loser_jti == winner_jti

	# outside the grace window the same presented jti must be rejected
	row.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
	db_session.add(row)
	await db_session.commit()
	assert await session_service.advance_session(db_session, row, presented) is None


@pytest.mark.asyncio
async def test_websocket_cookie_auth_rejects_revoked_session(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""websocket refresh-cookie auth must reject revoked sessions."""
	from unittest.mock import Mock

	from api.v1.service.authentication import (
		authenticate_websocket_refresh_cookie,
	)
	from api.v1.service.authentication import (
		sessions as session_service,
	)

	email = user_auth["email"]
	password = user_auth["password"]
	assert isinstance(email, str) and isinstance(password, str)
	user = auth_user(user_auth)
	_, cookie = await login(client, email, password)

	websocket = Mock()
	websocket.cookies = {REFRESH_COOKIE: cookie}

	authenticated = await authenticate_websocket_refresh_cookie(websocket)
	assert authenticated is not None
	assert str(authenticated.id) == str(user["id"])

	await session_service.revoke_all_sessions(db_session, authenticated.id)
	await db_session.commit()

	assert await authenticate_websocket_refresh_cookie(websocket) is None
