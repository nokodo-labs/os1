"""tests for ephemeral (persist=False) runs via POST /runs."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from api.models.message import MessageType
from api.schemas.message import MessageCreate, MessageSplice, RunBlockRef, TextContent
from api.schemas.runs import RunRequest
from api.tests.factories import make_principal
from api.v1.service.runs.thread_context import resolve_run_thread
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _empty_stream() -> AsyncGenerator[bytes]:
	if False:
		yield b""


# -- schema-level tests --


def test_run_request_persist_defaults_true() -> None:
	"""persist field defaults to True on RunRequest."""
	req = RunRequest(agent_id=TypeID(new_typeid("agent")))
	assert req.persist is True


def test_run_request_persist_false() -> None:
	"""persist=False is accepted and round-trips correctly."""
	req = RunRequest(
		agent_id=TypeID(new_typeid("agent")),
		input=MessageCreate(content=[TextContent(text="hi")]),
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


@pytest.mark.asyncio
async def test_thread_bound_ephemeral_run_loads_explicit_message_context(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	load = AsyncMock(return_value=(SDKThread(messages=[]), message_id))
	monkeypatch.setattr("api.v1.service.runs.thread_context.load_sdk_thread", load)
	monkeypatch.setattr(
		"api.v1.service.runs.thread_context.inject_system_instructions",
		AsyncMock(side_effect=lambda _agent, thread, **_kwargs: thread),
	)

	await resolve_run_thread(
		MagicMock(),
		AsyncMock(),
		make_principal(),
		thread_id,
		message_id,
		None,
		None,
		False,
	)

	assert load.await_args.kwargs["parent_id"] == message_id


@pytest.mark.asyncio
async def test_ephemeral_run_propagates_system_instruction_failure(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(
		"api.v1.service.runs.thread_context.inject_system_instructions",
		AsyncMock(side_effect=RuntimeError("system instructions unavailable")),
	)

	with pytest.raises(RuntimeError, match="system instructions unavailable"):
		await resolve_run_thread(
			MagicMock(),
			AsyncMock(),
			make_principal(),
			None,
			None,
			None,
			None,
			False,
		)


@pytest.mark.parametrize(
	"input_payload",
	[
		{"type": MessageType.ASSISTANT, "content": "not user"},
		{"content": "duplicate placement", "splice": {"parent_id": None}},
		{"content": []},
	],
)
def test_run_request_rejects_invalid_input_contract(
	input_payload: dict[str, object],
) -> None:
	with pytest.raises(ValidationError):
		RunRequest(
			agent_id=TypeID(new_typeid("agent")),
			input=MessageCreate.model_validate(input_payload),
		)


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
		"api.v1.routers.runs.start_ephemeral_run",
		_fake_start_ephemeral,
	)

	resp = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"content": "hello"},
			"persist": False,
		},
	)
	assert resp.status_code == 200
	assert resp.headers.get("content-type", "").startswith("text/event-stream")
	assert resp.headers.get("X-Accel-Buffering") == "no"


@pytest.mark.asyncio
async def test_ephemeral_run_accepts_image_only_input(
	client: AsyncClient,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)

	async def _start(**_kwargs: object) -> AsyncGenerator[bytes]:
		return _empty_stream()

	monkeypatch.setattr(
		"api.v1.routers.runs.start_ephemeral_run",
		_start,
	)
	response = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {
				"content": [{"type": "image", "url": "https://example.com/image.png"}]
			},
			"persist": False,
		},
	)
	assert response.status_code == 200


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

	async def _capture_launch_thread_run(*_args: object, **kwargs: object) -> TypeID:
		captured_kwargs.update(kwargs)
		return TypeID(new_typeid("run"))

	monkeypatch.setattr(
		"api.v1.routers.runs.launch_thread_run",
		_capture_launch_thread_run,
	)
	monkeypatch.setattr(
		"api.v1.routers.runs.subscribe_run_stream",
		lambda _run_id, _subscriber_id: _empty_stream(),
	)

	await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"thread_id": thread_id,
			"input": {"content": "hello"},
			"persist": False,
		},
	)
	assert captured_kwargs.get("persist") is False


@pytest.mark.asyncio
async def test_persisted_run_forwards_replacement_splice(
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
		json={"owner_id": user["id"], "title": "replace"},
	)
	thread_id = created.json()["id"]
	captured_kwargs: dict[str, object] = {}

	async def _capture(*_args: object, **kwargs: object) -> TypeID:
		captured_kwargs.update(kwargs)
		return TypeID(new_typeid("run"))

	monkeypatch.setattr(
		"api.v1.routers.runs.launch_thread_run",
		_capture,
	)
	monkeypatch.setattr(
		"api.v1.routers.runs.subscribe_run_stream",
		lambda _run_id, _subscriber_id: _empty_stream(),
	)
	root_id = new_typeid("msg")
	old_run_id = new_typeid("run")
	response = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"thread_id": thread_id,
			"splice": {
				"parent_id": None,
				"replaces": {
					"run_id": old_run_id,
					"run_head_message_id": root_id,
				},
			},
		},
	)
	assert response.status_code == 200
	splice = captured_kwargs["splice"]
	assert isinstance(splice, MessageSplice)
	assert isinstance(splice.replaces, RunBlockRef)
	assert str(splice.replaces.run_head_message_id) == root_id


@pytest.mark.asyncio
async def test_ephemeral_run_rejects_splice(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	response = await client.post(
		"/v1/runs",
		headers=headers,
		json={
			"agent_id": new_typeid("agent"),
			"input": {"content": "hello"},
			"persist": False,
			"splice": {"parent_id": None},
		},
	)
	assert response.status_code == 422
