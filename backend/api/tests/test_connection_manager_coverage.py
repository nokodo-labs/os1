"""Coverage-focused tests for the connection manager."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import WebSocket

from api.models.event import Event, EventScope
from api.v1.service import events as event_service
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
async def test_send_to_user_and_send_to_all_exception_paths() -> None:
	manager = ConnectionManager()

	ws_ok, _ = _make_websocket(fail_send=False)
	ws_fail, _ = _make_websocket(fail_send=True)

	await manager.connect(TypeID("u"), ws_ok)
	await manager.connect(TypeID("u"), ws_fail)

	await manager.send_to_user(TypeID("u"), {"a": 1})
	await manager.send_to_all({"type": "stream.pong"})

	await manager.disconnect(TypeID("u"), ws_ok)
	await manager.disconnect(TypeID("u"), ws_fail)


@pytest.mark.asyncio
async def test_fanout_event_routes_scope_payloads(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	seen: list[tuple[object, object, bool, dict[str, object]]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		seen.append((recipient_ids, user_id, broadcast, stream_payload))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

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

	await event_service.fanout_event(event)
	assert seen[0][:3] == (None, event.scope_id, False)

	event.scope = EventScope.PROJECT
	event.scope_id = None
	await event_service.fanout_event(event)
	assert len(seen) == 1

	event.user_id = None
	event.scope = EventScope.SYSTEM
	await event_service.fanout_event(event)
	assert seen[1] == (
		None,
		None,
		True,
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
		},
	)
