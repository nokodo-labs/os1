"""tests for ephemeral (persist=False) runs via POST /runs."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient

from api.schemas.runs import RunInput, RunRequest
from nokodo_ai.utils.typeid import TypeID, new_typeid


# -- schema-level tests --


def test_run_request_persist_defaults_true() -> None:
	"""persist field defaults to True on RunRequest."""
	req = RunRequest(agent_id=TypeID(new_typeid("agent")))
	assert req.persist is True


def test_run_request_persist_false() -> None:
	"""persist=False is accepted and round-trips correctly."""
	req = RunRequest(
		agent_id=TypeID(new_typeid("agent")),
		input=RunInput(text="hi"),
		persist=False,
	)
	assert req.persist is False
	assert req.thread_id is None


def test_run_request_persist_false_with_thread_id() -> None:
	"""persist=False can still carry a thread_id (server decides behavior)."""
	tid = TypeID(new_typeid("thread"))
	req = RunRequest(agent_id=TypeID(new_typeid("agent")), thread_id=tid, persist=False)
	assert req.persist is False
	assert req.thread_id == tid


# -- router-level tests --


@pytest.mark.asyncio
async def test_ephemeral_run_requires_input(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""POST /runs without thread_id or input returns 422."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	resp = await client.post(
		"/v1/runs",
		headers=headers,
		json={"agent_id": new_typeid("agent"), "persist": False},
	)
	assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ephemeral_run_streams_and_returns_sse(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""POST /runs without thread_id but with input returns an SSE stream."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	async def _fake_start_ephemeral(
		*_args: object, **_kwargs: object
	) -> AsyncGenerator[bytes]:
		"""yield a single done frame."""

		async def _gen() -> AsyncGenerator[bytes]:
			yield b"event: done\ndata: {}\n\n"

		return _gen()

	monkeypatch.setattr(
		"api.v1.routers.runs.runs_service.start_ephemeral_run",
		_fake_start_ephemeral,
	)

	resp = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"text": "hello"},
			"persist": False,
		},
	)
	assert resp.status_code == 200
	assert resp.headers.get("content-type", "").startswith("text/event-stream")
	assert resp.headers.get("X-Accel-Buffering") == "no"


@pytest.mark.asyncio
async def test_ephemeral_run_not_streaming_returns_501(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""POST /runs with stream=false returns 501 (not implemented)."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	resp = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"text": "hello"},
			"persist": False,
			"stream": False,
		},
	)
	assert resp.status_code == 501


@pytest.mark.asyncio
async def test_persisted_run_forwards_persist_flag(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""POST /runs with thread_id passes persist kwarg to service layer."""
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

	captured_kwargs: dict[str, object] = {}

	async def _capture_start_thread_run(
		*_args: object, **kwargs: object
	) -> AsyncGenerator[bytes]:
		captured_kwargs.update(kwargs)

		async def _empty() -> AsyncGenerator[bytes]:
			if False:
				yield b""

		return _empty()

	monkeypatch.setattr(
		"api.v1.routers.runs.runs_service.start_thread_run",
		_capture_start_thread_run,
	)

	await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"thread_id": thread_id,
			"input": {"text": "hello"},
			"persist": False,
		},
	)
	assert captured_kwargs.get("persist") is False
