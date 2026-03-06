"""Coverage-focused tests for the connection manager."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import WebSocket

from api.models.event import Event, EventScope
from api.v1.service.events import ConnectionManager
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _make_websocket(
	*,
	fail_send: bool,
) -> tuple[WebSocket, list[dict[str, object]]]:
	sent: list[dict[str, object]] = []

	async def _send(message: object) -> None:
		if not isinstance(message, dict):
			raise AssertionError("expected asgi message dict")
		if fail_send and message.get("type") == "websocket.send":
			raise RuntimeError("send failed")
		sent.append(message)

	async def _receive() -> dict[str, object]:
		return {"type": "websocket.connect"}

	scope = {
		"type": "websocket",
		"asgi": {"spec_version": "2.0"},
		"path": "/",
		"raw_path": b"/",
		"scheme": "ws",
		"query_string": b"",
		"headers": [],
		"client": ("test", 1234),
		"server": ("test", 80),
		"subprotocols": [],
	}

	ws = WebSocket(scope, _receive, _send)
	return ws, sent


@pytest.mark.asyncio
async def test_send_to_user_and_broadcast_exception_paths() -> None:
	manager = ConnectionManager()

	ws_ok, _ = _make_websocket(fail_send=False)
	ws_fail, _ = _make_websocket(fail_send=True)

	await manager.connect("u", ws_ok)
	await manager.connect("u", ws_fail)

	await manager.send_to_user("u", {"a": 1})
	await manager.broadcast({"b": 2})

	await manager.disconnect("u", ws_ok)
	await manager.disconnect("u", ws_fail)


@pytest.mark.asyncio
async def test_broadcast_event_routes() -> None:
	seen_send: list[str] = []
	seen_broadcast: list[dict[str, object]] = []

	class _Manager(ConnectionManager):
		async def send_to_user(self, user_id: str, data: dict[str, object]) -> None:
			_ = data
			seen_send.append(user_id)

		async def broadcast(self, data: dict[str, object]) -> None:
			seen_broadcast.append(data)

	manager = _Manager()

	event = Event(
		scope=EventScope.THREAD,
		scope_id=None,
		type="t",
		data={},
		expires_at=None,
		version=1,
		user_id=str(TypeID(new_typeid("user"))),
		thread_id=None,
		message_id=None,
		task_id=None,
		project_id=None,
		metadata_={},
	)
	event.created_at = datetime.now(UTC)

	await manager.broadcast_event(event)
	assert seen_send == [str(event.user_id)]

	event.user_id = None
	event.scope = EventScope.PROJECT
	await manager.broadcast_event(event)
	assert seen_broadcast
