"""Coverage-focused tests for the connection manager."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import WebSocket

from api.models.event import Event, EventScope
from api.v1.service.events import ConnectionManager
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _make_websocket(
	fail_send: bool,
) -> tuple[WebSocket, list[dict[str, object]]]:
	sent: list[dict[str, object]] = []

	async def _send(message: object) -> None:
		if not isinstance(message, dict):
			raise AssertionError("expected asgi message dict")
		asgi_message = {
			key: value for key, value in message.items() if isinstance(key, str)
		}
		if fail_send and asgi_message.get("type") == "websocket.send":
			raise RuntimeError("send failed")
		sent.append(asgi_message)

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

	await manager.connect(TypeID("u"), ws_ok)
	await manager.connect(TypeID("u"), ws_fail)

	await manager.send_to_user(TypeID("u"), {"a": 1})
	await manager.broadcast({"type": "stream.pong"})

	await manager.disconnect(TypeID("u"), ws_ok)
	await manager.disconnect(TypeID("u"), ws_fail)


@pytest.mark.asyncio
async def test_broadcast_event_routes() -> None:
	seen_send: list[str] = []
	seen_broadcast: list[dict[str, object]] = []

	class _Manager(ConnectionManager):
		async def send_to_user(self, user_id: TypeID, data: dict[str, object]) -> None:
			_ = data
			seen_send.append(str(user_id))

		async def broadcast(self, data: dict[str, object]) -> None:
			seen_broadcast.append(data)

	manager = _Manager()

	event = Event(
		scope=EventScope.USER,
		scope_id=TypeID(new_typeid("user")),
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
	assert seen_send == [str(event.scope_id)]

	event.scope = EventScope.PROJECT
	event.scope_id = None
	await manager.broadcast_event(event)
	assert seen_broadcast == []

	event.user_id = None
	event.scope = EventScope.SYSTEM
	await manager.broadcast_event(event)
	assert seen_broadcast == [
		{
			"id": str(event.id),
			"type": "t",
			"scope": event.scope.value,
			"scope_id": None,
			"data": {},
			"version": 1,
			"user_id": None,
			"thread_id": None,
			"message_id": None,
			"task_id": None,
			"project_id": None,
			"calendar_id": None,
			"calendar_event_id": None,
			"reminder_list_id": None,
			"reminder_id": None,
			"created_at": event.created_at.isoformat(),
			"origin_session_id": None,
		}
	]
