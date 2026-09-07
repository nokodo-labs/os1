"""Coverage-focused tests for thread run/stream and delete authorization."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

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
async def test_create_and_run_refusal_is_an_http_error_not_a_frame(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a run that will not start never opens a 200 stream, and leaves no thread.

	the launch happens before the response and on the same transaction, so the
	client reads the refusal the way it reads any other rejected request, and
	the thread it would have answered in is rolled back with it.
	"""
	from fastapi import HTTPException, status
	from sqlalchemy import func, select

	from api.models.thread import Thread

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	async def _refuse(*_args: object, **_kwargs: object) -> str:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="this agent already has a run in this conversation",
		)

	monkeypatch.setattr(
		"api.v1.service.runs.launch.launch_thread_run",
		_refuse,
	)

	client_thread_id = new_typeid("thread")
	resp = await client.post(
		"/v1/threads/create_and_run",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"thread_id": client_thread_id,
			"input": {"content": "hi"},
			"stream": True,
		},
	)

	assert resp.status_code == 409
	assert "event: error" not in resp.text
	# the client-supplied id was never used, and no thread was created under
	# a generated one either - a refused run leaves nothing behind.
	assert await db_session.get(Thread, client_thread_id) is None
	owned = await db_session.scalar(
		select(func.count()).select_from(Thread).where(Thread.owner_id == user["id"])
	)
	assert owned == 0


@pytest.mark.asyncio
async def test_create_and_run_refusal_leaves_no_generated_thread(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the generated-id branch rolls back too.

	a request with no client thread id takes a different creation branch, so
	the rollback has to be proven there rather than inferred from the one that
	supplies an id.
	"""
	from fastapi import HTTPException, status
	from sqlalchemy import func, select

	from api.models.thread import Thread

	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	async def _refuse(*_args: object, **_kwargs: object) -> str:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="agent not found",
		)

	monkeypatch.setattr(
		"api.v1.service.runs.launch.launch_thread_run",
		_refuse,
	)

	resp = await client.post(
		"/v1/threads/create_and_run",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"content": "hi"},
			"stream": True,
		},
	)

	assert resp.status_code == 404
	assert "event: error" not in resp.text
	owned = await db_session.scalar(
		select(func.count()).select_from(Thread).where(Thread.owner_id == user["id"])
	)
	assert owned == 0


@pytest.mark.parametrize(
	("raised", "expected_reason"),
	[
		("bus", "unavailable"),
		("bug", "internal_error"),
	],
)
@pytest.mark.asyncio
async def test_create_and_run_stream_failure_closes_with_its_own_reason(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
	raised: str,
	expected_reason: str,
) -> None:
	"""a failure after the first frame closes the stream, and says which kind.

	the status line and ``thread_created`` are already on the wire, so this
	cannot raise; and an unreachable backend is worth retrying, which
	``internal_error`` would tell the client to report as a bug instead.
	"""

	from api.v1.service.runs.bus import RunBusUnavailableError

	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	async def _fail(*_args: object, **_kwargs: object) -> AsyncGenerator[bytes]:
		if raised == "bus":
			raise RunBusUnavailableError("read_run_route")
		raise RuntimeError("boom")
		yield b""

	async def _launch(*_args: object, **_kwargs: object) -> str:
		return new_typeid("run")

	monkeypatch.setattr("api.v1.service.runs.launch.launch_thread_run", _launch)
	monkeypatch.setattr("api.v1.service.runs.launch.subscribe_run_stream", _fail)

	resp = await client.post(
		"/v1/threads/create_and_run",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"content": "hi"},
			"stream": True,
		},
	)

	assert resp.status_code == 200
	frames = resp.text
	assert "event: thread_created" in frames
	error_payload = json.loads(
		frames.split("event: error\ndata: ", 1)[1].split("\n\n", 1)[0]
	)
	# the one shared payload shape, whichever arm produced it.
	assert set(error_payload) == {
		"thread_id",
		"agent_id",
		"reason",
		"run_id",
		"partial_message_id",
	}
	assert error_payload["reason"] == expected_reason
	assert frames.rstrip().endswith("event: done\ndata: {}")


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
