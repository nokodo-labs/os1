"""Tests for the redis-cached principal and session validity layer."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user_session import UserSession
from api.v1.service.authentication import cache as auth_cache
from api.v1.service.authentication import sessions as session_service


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


@pytest.mark.asyncio
async def test_principal_snapshot_roundtrip(
	client: AsyncClient, user_auth: dict[str, object]
) -> None:
	"""an authenticated request populates the principal cache."""
	user = auth_user(user_auth)
	resp = await client.get(
		f"/v1/users/{user['id']}",
		headers=auth_headers(user_auth),
	)
	assert resp.status_code == 200

	snapshot = await auth_cache.get_principal_snapshot(str(user["id"]))
	assert snapshot is not None
	raw_subject = snapshot["subject"]
	assert isinstance(raw_subject, dict)
	subject = {str(k): v for k, v in raw_subject.items()}
	assert subject["email"] == user["email"]
	assert subject["kind"] == "user"
	assert "hashed_password" not in subject


@pytest.mark.asyncio
async def test_cached_principal_serves_requests(
	client: AsyncClient, user_auth: dict[str, object]
) -> None:
	"""requests keep working when served from the cached snapshot."""
	user = auth_user(user_auth)
	headers = auth_headers(user_auth)
	first = await client.get(f"/v1/users/{user['id']}", headers=headers)
	assert first.status_code == 200
	second = await client.get(f"/v1/users/{user['id']}", headers=headers)
	assert second.status_code == 200
	assert second.json()["email"] == user["email"]


@pytest.mark.asyncio
async def test_user_update_invalidates_principal(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""a user patch drops the cached snapshot so changes apply immediately."""
	target = auth_user(user_auth)
	headers = auth_headers(user_auth)
	warm = await client.get(f"/v1/users/{target['id']}", headers=headers)
	assert warm.status_code == 200
	assert await auth_cache.get_principal_snapshot(str(target["id"])) is not None

	patch = await client.patch(
		f"/v1/users/{target['id']}",
		headers=auth_headers(admin_auth),
		json={"is_active": False},
	)
	assert patch.status_code == 200
	assert await auth_cache.get_principal_snapshot(str(target["id"])) is None

	blocked = await client.get(f"/v1/users/{target['id']}", headers=headers)
	assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_revoked_session_rejected_on_next_request(
	client: AsyncClient, user_auth: dict[str, object]
) -> None:
	"""session revocation kills access tokens on the next request, not at expiry."""
	user = auth_user(user_auth)
	headers = auth_headers(user_auth)
	ok = await client.get(f"/v1/users/{user['id']}", headers=headers)
	assert ok.status_code == 200

	revoke = await client.post(
		f"/v1/users/{user['id']}/sessions/revoke",
		headers=headers,
	)
	assert revoke.status_code == 200

	rejected = await client.get(f"/v1/users/{user['id']}", headers=headers)
	assert rejected.status_code == 401


@pytest.mark.asyncio
async def test_session_validity_cache_fill_and_write_through(
	client: AsyncClient,
	user_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""validity fills from the DB and revocation write-through wins over fills."""
	user = auth_user(user_auth)
	result = await db_session.execute(
		select(UserSession)
		.where(UserSession.user_id == str(user["id"]))
		.order_by(UserSession.created_at.desc())
	)
	row = result.scalars().first()
	assert row is not None

	assert await session_service.session_alive(db_session, row.id) is True
	assert await auth_cache.get_session_validity(row.id) is True

	await auth_cache.mark_session_revoked(row.id)
	# nx fill must not resurrect the revoked flag
	await auth_cache.fill_session_validity(row.id, True)
	assert await auth_cache.get_session_validity(row.id) is False


@pytest.mark.asyncio
async def test_unknown_session_id_is_dead(
	db_session: AsyncSession,
) -> None:
	"""a sid that has no session row is treated as revoked."""
	from nokodo_ai.utils.typeid import TypeID, new_typeid

	ghost = TypeID(new_typeid("sess"))
	assert await session_service.session_alive(db_session, ghost) is False


@pytest.mark.asyncio
async def test_role_change_invalidates_member_principals(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""changing a role's permissions drops cached principals of its members."""
	admin_headers = auth_headers(admin_auth)
	target = auth_user(user_auth)
	target_headers = auth_headers(user_auth)
	unique = uuid4().hex[:10]

	role_resp = await client.post(
		"/v1/roles",
		headers=admin_headers,
		json={
			"name": f"cache-test-{unique}",
			"default_permissions": {"action_permissions": ["prompts:read"]},
		},
	)
	assert role_resp.status_code == 201
	role_id = role_resp.json()["id"]

	assign = await client.patch(
		f"/v1/users/{target['id']}",
		headers=admin_headers,
		json={"role_ids": [role_id]},
	)
	assert assign.status_code == 200

	# warm the cache with the role attached
	warm = await client.get(f"/v1/users/{target['id']}", headers=target_headers)
	assert warm.status_code == 200
	assert await auth_cache.get_principal_snapshot(str(target["id"])) is not None

	# updating the role's permissions must drop the member's snapshot
	update = await client.patch(
		f"/v1/roles/{role_id}",
		headers=admin_headers,
		json={"default_permissions": {"action_permissions": ["prompts:manage"]}},
	)
	assert update.status_code == 200
	assert await auth_cache.get_principal_snapshot(str(target["id"])) is None
