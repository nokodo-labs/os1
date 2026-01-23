"""Coverage-focused tests for the events websocket endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import WebSocket
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


# WebSocket tests need Origin header for CSRF protection.
ALLOWED_ORIGIN = "http://localhost:888"


class _FakeWebSocket:
	def __init__(self, incoming: list[object], cookies: dict[str, str] | None = None):
		self._incoming = list(incoming)
		self.sent: list[dict[str, object]] = []
		self.closed: list[tuple[int, str | None]] = []
		self.cookies = cookies or {}
		# Mock headers for Origin validation
		self.headers = {"origin": ALLOWED_ORIGIN}

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


class _FakeWebSocketNoOrigin(_FakeWebSocket):
	"""Fake WebSocket without Origin header for CSRF rejection tests."""

	def __init__(self, incoming: list[object], cookies: dict[str, str] | None = None):
		super().__init__(incoming, cookies)
		self.headers = {}


def test_events_stream_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
	from api.main import app
	from api.v1.routers import events as events_router

	async def _nope(_websocket):
		return None

	monkeypatch.setattr(
		events_router.auth_service,
		"authenticate_websocket_refresh_cookie",
		_nope,
	)

	# Origin validation is bypassed in TestClient, so we test the auth path
	def _origin_ok(_websocket) -> bool:
		return True

	monkeypatch.setattr(
		events_router.auth_service, "is_websocket_origin_allowed", _origin_ok
	)

	with TestClient(app) as client:
		with pytest.raises(WebSocketDisconnect) as exc:
			with client.websocket_connect("/v1/events/stream"):
				pass
		assert exc.value.code == 4001


def test_events_stream_ping(monkeypatch: pytest.MonkeyPatch) -> None:
	from api.main import app
	from api.v1.routers import events as events_router
	from api.v1.service.events import ConnectionManager

	async def _ok(_websocket):
		return SimpleNamespace(id="user_1", is_active=True)

	def _origin_ok(_websocket) -> bool:
		return True

	manager = ConnectionManager()
	monkeypatch.setattr(
		events_router.auth_service,
		"authenticate_websocket_refresh_cookie",
		_ok,
	)
	monkeypatch.setattr(
		events_router.auth_service, "is_websocket_origin_allowed", _origin_ok
	)
	monkeypatch.setattr(events_router.event_service, "event_connections", manager)

	with TestClient(app) as client:
		with client.websocket_connect("/v1/events/stream") as ws:
			connected = ws.receive_json()
			assert connected["type"] == "stream.connected"
			ws.send_json({"type": "ping"})
			pong = ws.receive_json()
			assert pong["type"] == "stream.pong"


@pytest.mark.asyncio
async def test_events_stream_loop_disconnect_and_finally(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events as events_router

	async def _ok(_websocket):
		return SimpleNamespace(id="user_1", is_active=True)

	calls: list[tuple[str, str]] = []

	class _Mgr:
		async def connect(self, user_id: str, websocket: object) -> None:
			calls.append(("connect", user_id))

		async def disconnect(self, user_id: str, websocket: object) -> None:
			calls.append(("disconnect", user_id))

	monkeypatch.setattr(
		events_router.auth_service,
		"authenticate_websocket_refresh_cookie",
		_ok,
	)
	monkeypatch.setattr(events_router.event_service, "event_connections", _Mgr())

	ws = _FakeWebSocket(
		[
			{"type": "noop"},
			{"type": "ping"},
			WebSocketDisconnect(code=1000),
		],
		cookies={"refresh_token": "valid"},
	)

	await events_router.events_stream(cast(WebSocket, ws))

	assert ws.sent[0]["type"] == "stream.connected"
	assert ws.sent[1] == {"type": "stream.pong"}
	assert calls == [("connect", "user_1"), ("disconnect", "user_1")]


@pytest.mark.asyncio
async def test_events_stream_origin_rejected(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""WebSocket without valid Origin should be rejected."""
	from api.v1.routers import events as events_router

	ws = _FakeWebSocketNoOrigin([])
	await events_router.events_stream(cast(WebSocket, ws))
	assert ws.closed == [(4003, "origin not allowed")]


@pytest.mark.asyncio
async def test_events_stream_unauthorized_closes_and_returns(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events as events_router

	async def _nope(_websocket):
		return None

	monkeypatch.setattr(
		events_router.auth_service,
		"authenticate_websocket_refresh_cookie",
		_nope,
	)

	ws = _FakeWebSocket([], cookies={})
	await events_router.events_stream(cast(WebSocket, ws))
	assert ws.closed == [(4001, "unauthorized")]


@pytest.mark.asyncio
async def test_events_stream_exception_path_still_disconnects(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.routers import events as events_router

	async def _ok(_websocket):
		return SimpleNamespace(id="user_1", is_active=True)

	calls: list[tuple[str, str]] = []

	class _Mgr:
		async def connect(self, user_id: str, websocket: object) -> None:
			calls.append(("connect", user_id))

		async def disconnect(self, user_id: str, websocket: object) -> None:
			calls.append(("disconnect", user_id))

	monkeypatch.setattr(
		events_router.auth_service,
		"authenticate_websocket_refresh_cookie",
		_ok,
	)
	monkeypatch.setattr(events_router.event_service, "event_connections", _Mgr())

	ws = _FakeWebSocket([ValueError("boom")], cookies={"refresh_token": "valid"})
	await events_router.events_stream(cast(WebSocket, ws))
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
async def test_authenticate_websocket_cookie_returns_none_without_cookie() -> None:
	from api.v1.service import auth as auth_service

	ws = _FakeWebSocket([], cookies={})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_decode_error_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from authlib.jose import JoseError

	from api.v1.service import auth as auth_service

	def _boom(*_args, **_kwargs):
		raise JoseError("bad token")

	monkeypatch.setattr(auth_service, "decode_jwt_token", _boom)
	ws = _FakeWebSocket([], cookies={"refresh_token": "bad"})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_wrong_type_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service import auth as auth_service

	def _decode(*_args, **_kwargs):
		return {"sub": "user_123", "typ": "access"}  # Not a refresh token

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)
	ws = _FakeWebSocket([], cookies={"refresh_token": "access_token"})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_missing_sub_returns_none(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service import auth as auth_service

	def _decode(*_args, **_kwargs):
		return {"typ": "refresh", "no_sub": "x"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)
	ws = _FakeWebSocket([], cookies={"refresh_token": "token"})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_user_not_found_returns_none(
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service import auth as auth_service
	from nokodo_ai.utils.typeid import new_typeid

	monkeypatch.setattr(
		auth_service, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": new_typeid("user"), "typ": "refresh"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)
	ws = _FakeWebSocket([], cookies={"refresh_token": "token"})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_inactive_user_returns_none(
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.models.user import User
	from api.v1.service import auth as auth_service
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
		auth_service, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": str(inactive.id), "typ": "refresh"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)
	ws = _FakeWebSocket([], cookies={"refresh_token": "token"})
	assert (
		await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	) is None


@pytest.mark.asyncio
async def test_authenticate_websocket_cookie_active_user_is_returned(
	test_user: dict,
	db_session,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service import auth as auth_service

	monkeypatch.setattr(
		auth_service, "AsyncSessionLocal", _AsyncSessionFactory(db_session)
	)

	def _decode(*_args, **_kwargs):
		return {"sub": str(test_user["id"]), "typ": "refresh"}

	monkeypatch.setattr(auth_service, "decode_jwt_token", _decode)
	ws = _FakeWebSocket([], cookies={"refresh_token": "token"})
	user = await auth_service.authenticate_websocket_refresh_cookie(cast(WebSocket, ws))
	assert user is not None
	assert str(user.id) == str(test_user["id"])
