"""Coverage-focused tests for the events websocket endpoint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


class _FakeWebSocket:
	def __init__(self, incoming: list[object]):
		self._incoming = list(incoming)
		self.sent: list[dict[str, object]] = []
		self.closed: list[tuple[int, str | None]] = []

	async def close(self, code: int = 1000, reason: str | None = None) -> None:
		self.closed.append((code, reason))

	async def send_json(self, data: dict[str, object]) -> None:
		self.sent.append(data)

	async def receive_json(self) -> dict[str, object]:
		if not self._incoming:
			raise AssertionError("no more incoming websocket messages")
		next_item = self._incoming.pop(0)
		if isinstance(next_item, Exception):
			raise next_item
		if not isinstance(next_item, dict):
			raise AssertionError("expected dict or Exception")
		return next_item


def test_events_stream_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
	from api.main import app
	from api.v1.routers import events_stream as events_stream_router

	async def _nope(_token: str | None):
		return None

	monkeypatch.setattr(events_stream_router, "_authenticate_websocket", _nope)

	with TestClient(app) as client:
		with pytest.raises(WebSocketDisconnect) as exc:
			with client.websocket_connect("/v1/events/stream?token=x"):
				pass
		assert exc.value.code == 4001


def test_events_stream_ping(monkeypatch: pytest.MonkeyPatch) -> None:
	from api.main import app
	from api.v1.routers import events_stream as events_stream_router
	from api.v1.service.connection_manager import ConnectionManager

	async def _ok(_token: str | None):
		return SimpleNamespace(id="user_1", is_active=True)

	manager = ConnectionManager()
	monkeypatch.setattr(events_stream_router, "_authenticate_websocket", _ok)
	monkeypatch.setattr(events_stream_router, "event_connections", manager)

	with TestClient(app) as client:
		with client.websocket_connect("/v1/events/stream?token=x") as ws:
			connected = ws.receive_json()
			assert connected["type"] == "stream.connected"
			ws.send_json({"type": "ping"})
			pong = ws.receive_json()
			assert pong["type"] == "stream.pong"


@pytest.mark.asyncio
async def test_events_stream_loop_disconnect_and_finally(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	async def _ok(_token: str | None):
		return SimpleNamespace(id="user_1", is_active=True)

	calls: list[tuple[str, str]] = []

	class _Mgr:
		async def connect(self, user_id: str, websocket) -> None:  # noqa: ANN001
			calls.append(("connect", user_id))

		async def disconnect(self, user_id: str, websocket) -> None:  # noqa: ANN001
			calls.append(("disconnect", user_id))

	monkeypatch.setattr(events_stream_router, "_authenticate_websocket", _ok)
	monkeypatch.setattr(events_stream_router, "event_connections", _Mgr())

	ws = _FakeWebSocket(
		[
			{"type": "noop"},
			{"type": "ping"},
			WebSocketDisconnect(code=1000),
		]
	)

	await events_stream_router.events_stream(ws, token="x")

	assert ws.sent[0]["type"] == "stream.connected"
	assert ws.sent[1] == {"type": "stream.pong"}
	assert calls == [("connect", "user_1"), ("disconnect", "user_1")]


@pytest.mark.asyncio
async def test_events_stream_unauthorized_closes_and_returns(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	async def _nope(_token: str | None):
		return None

	monkeypatch.setattr(events_stream_router, "_authenticate_websocket", _nope)

	ws = _FakeWebSocket([])
	await events_stream_router.events_stream(ws, token=None)
	assert ws.closed == [(4001, "unauthorized")]


@pytest.mark.asyncio
async def test_events_stream_exception_path_still_disconnects(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	async def _ok(_token: str | None):
		return SimpleNamespace(id="user_1", is_active=True)

	calls: list[tuple[str, str]] = []

	class _Mgr:
		async def connect(self, user_id: str, websocket) -> None:  # noqa: ANN001
			calls.append(("connect", user_id))

		async def disconnect(self, user_id: str, websocket) -> None:  # noqa: ANN001
			calls.append(("disconnect", user_id))

	monkeypatch.setattr(events_stream_router, "_authenticate_websocket", _ok)
	monkeypatch.setattr(events_stream_router, "event_connections", _Mgr())

	ws = _FakeWebSocket([ValueError("boom")])
	await events_stream_router.events_stream(ws, token="x")
	assert calls == [("connect", "user_1"), ("disconnect", "user_1")]


class _AsyncSessionFactory:
	def __init__(self, session):
		self._session = session

	def __call__(self):
		return self

	async def __aenter__(self):
		return self._session

	async def __aexit__(self, exc_type, exc, tb):
		_ = (exc_type, exc, tb)
		return False


@pytest.mark.asyncio
async def test_authenticate_websocket_returns_none_without_token() -> None:
	from api.v1.routers import events_stream as events_stream_router

	assert await events_stream_router._authenticate_websocket(None) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_decode_error_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	def _boom(*_args, **_kwargs):
		raise RuntimeError("bad token")

	monkeypatch.setattr(events_stream_router, "decode_jwt_token", _boom)
	assert await events_stream_router._authenticate_websocket("x") is None


@pytest.mark.asyncio
async def test_authenticate_websocket_missing_sub_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	def _decode(*_args, **_kwargs):
		return {"no_sub": "x"}

	monkeypatch.setattr(events_stream_router, "decode_jwt_token", _decode)
	assert await events_stream_router._authenticate_websocket("x") is None


@pytest.mark.asyncio
async def test_authenticate_websocket_user_not_found_returns_none(
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router
	from nokodo_ai.utils.typeid import new_typeid

	monkeypatch.setattr(
		events_stream_router, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": new_typeid("user")}

	monkeypatch.setattr(events_stream_router, "decode_jwt_token", _decode)
	assert await events_stream_router._authenticate_websocket("x") is None


@pytest.mark.asyncio
async def test_authenticate_websocket_inactive_user_returns_none(
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.models.user import User
	from api.v1.routers import events_stream as events_stream_router
	from nokodo_ai.utils.security import hash_password

	inactive = User(
		email="inactive@example.com",
		hashed_password=hash_password("password"),
		is_active=False,
		is_superuser=False,
	)
	db_session.add(inactive)
	await db_session.commit()
	await db_session.refresh(inactive)

	monkeypatch.setattr(
		events_stream_router, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": str(inactive.id)}

	monkeypatch.setattr(events_stream_router, "decode_jwt_token", _decode)
	assert await events_stream_router._authenticate_websocket("x") is None


@pytest.mark.asyncio
async def test_authenticate_websocket_active_user_is_returned(
	test_user: dict,
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events_stream as events_stream_router

	monkeypatch.setattr(
		events_stream_router, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": str(test_user["id"])}

	monkeypatch.setattr(events_stream_router, "decode_jwt_token", _decode)
	user = await events_stream_router._authenticate_websocket("x")
	assert user is not None
	assert str(user.id) == str(test_user["id"])
