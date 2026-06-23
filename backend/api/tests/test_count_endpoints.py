"""Tests for resource count endpoint authorization."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


_ACCESS_SCOPED_COUNT_PATHS = (
	"/v1/agents/count",
	"/v1/groups/count",
	"/v1/calendars/count",
	"/v1/notes/count",
	"/v1/reminder-lists/count",
	"/v1/tasks/count",
	"/v1/threads/count",
)

_SENSITIVE_COUNT_PATHS = (
	"/v1/users/count",
	"/v1/prompts/count",
	"/v1/roles/count",
)


def _auth_headers(auth: dict[str, object]) -> dict[str, str]:
	headers = auth["headers"]
	if not isinstance(headers, dict):
		raise AssertionError("auth fixture is missing headers")

	validated: dict[str, str] = {}
	for key, value in headers.items():
		if not isinstance(key, str) or not isinstance(value, str):
			raise AssertionError("auth headers must be strings")
		validated[key] = value
	return validated


def _auth_user(auth: dict[str, object]) -> dict[str, object]:
	user = auth["user"]
	if not isinstance(user, dict):
		raise AssertionError("auth fixture is missing user")
	validated: dict[str, object] = {}
	for key, value in user.items():
		if not isinstance(key, str):
			raise AssertionError("auth user keys must be strings")
		validated[key] = value
	return validated


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _ACCESS_SCOPED_COUNT_PATHS)
async def test_access_scoped_counts_allow_authenticated_users(
	client: AsyncClient,
	user_auth: dict[str, object],
	path: str,
) -> None:
	response = await client.get(path, headers=_auth_headers(user_auth))

	assert response.status_code == 200
	assert isinstance(response.json(), int)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", _SENSITIVE_COUNT_PATHS)
async def test_sensitive_counts_reject_regular_users(
	client: AsyncClient,
	user_auth: dict[str, object],
	path: str,
) -> None:
	response = await client.get(path, headers=_auth_headers(user_auth))

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_memory_count_requires_owner_filter(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	user = _auth_user(user_auth)
	user_id = user["id"]
	if not isinstance(user_id, str):
		raise AssertionError("auth user is missing id")

	response = await client.get(
		"/v1/memories/count",
		params={"owner_id": user_id},
		headers=_auth_headers(user_auth),
	)

	assert response.status_code == 200
	assert isinstance(response.json(), int)


@pytest.mark.asyncio
async def test_hidden_thread_count_remains_admin_only(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	response = await client.get(
		"/v1/threads/count",
		params={"include_hidden": True},
		headers=_auth_headers(user_auth),
	)

	assert response.status_code == 403
