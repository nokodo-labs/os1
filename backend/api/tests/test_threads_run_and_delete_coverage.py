"""Coverage-focused tests for thread run/stream and delete authorization."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_thread_run_stream_headers(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	created = await client.post(
		"/v1/threads",
		headers=headers,
		json={"owner_id": user["id"], "title": "t"},
	)
	assert created.status_code == 201
	thread_id = created.json()["id"]

	async def _stream(*_args: object, **_kwargs: object) -> AsyncGenerator[bytes]:
		if False:
			yield b""

	async def _fake_launch_thread_run(*_args: object, **_kwargs: object) -> str:
		return new_typeid("run")

	monkeypatch.setattr(
		"api.v1.routers.runs.launch_thread_run",
		_fake_launch_thread_run,
	)
	monkeypatch.setattr(
		"api.v1.routers.runs.subscribe_run_stream",
		lambda _run_id, _subscriber_id: _stream(),
	)

	resp = await client.post(
		"/v1/runs",
		headers=headers,
		json={"agent_id": new_typeid("agent"), "thread_id": thread_id, "input": None},
	)
	assert resp.status_code == 200
	assert resp.headers.get("X-Accel-Buffering") == "no"


@pytest.mark.asyncio
async def test_delete_thread_forbidden_for_non_owner(
	client: AsyncClient,
	user_auth: dict[str, object],
	admin_auth: dict[str, object],
) -> None:
	owner_headers = user_auth["headers"]
	assert isinstance(owner_headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)

	created = await client.post(
		"/v1/threads",
		headers=owner_headers,
		json={"owner_id": user["id"], "title": "t"},
	)
	assert created.status_code == 201
	thread_id = created.json()["id"]

	# create a second non-admin user and attempt delete
	email = f"other-{new_typeid('user')}@example.com"
	username = f"other{new_typeid('user')[-12:]}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	other_headers = {"Authorization": f"Bearer {token}"}

	resp = await client.delete(
		f"/v1/threads/{thread_id}",
		headers=other_headers,
	)
	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_thread_forbidden_when_editor_not_owner(
	client: AsyncClient,
	user_auth: dict[str, object],
	admin_auth: dict[str, object],
) -> None:
	owner_headers = user_auth["headers"]
	assert isinstance(owner_headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)

	created = await client.post(
		"/v1/threads",
		headers=owner_headers,
		json={"owner_id": user["id"], "title": "t"},
	)
	assert created.status_code == 201
	thread_id = created.json()["id"]

	# Create a second non-admin user.
	email = f"editor-{new_typeid('user')}@example.com"
	username = f"editor{new_typeid('user')[-12:]}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201
	other_user_id = user_resp.json()["id"]

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	other_token = login_resp.json()["access_token"]
	other_headers = {"Authorization": f"Bearer {other_token}"}

	# add them as a participant, but they are not the owner.
	acl_resp = await client.post(
		f"/v1/threads/{thread_id}/participants",
		headers=owner_headers,
		json={"user_ids": [other_user_id]},
	)
	assert acl_resp.status_code == 201
	accept_resp = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{other_user_id}/invite/accept",
		headers=other_headers,
	)
	assert accept_resp.status_code == 200

	resp = await client.delete(
		f"/v1/threads/{thread_id}",
		headers=other_headers,
	)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_thread_as_owner_soft_deletes(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	created = await client.post(
		"/v1/threads",
		headers=headers,
		json={"owner_id": user["id"], "title": "t"},
	)
	assert created.status_code == 201
	thread_id = created.json()["id"]

	deleted = await client.delete(
		f"/v1/threads/{thread_id}",
		headers=headers,
	)
	assert deleted.status_code == 204

	missing = await client.get(f"/v1/threads/{thread_id}", headers=headers)
	assert missing.status_code in {403, 404}
