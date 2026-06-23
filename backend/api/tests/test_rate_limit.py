"""tests for rate limiting middleware and middleware utils."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from api.middleware._utils import append_header, get_client_ip, get_header


# -- middleware _utils tests --


def test_get_header_returns_value_when_present() -> None:
	scope = {"headers": [(b"x-forwarded-for", b"1.2.3.4"), (b"host", b"localhost")]}
	assert get_header(scope, b"x-forwarded-for") == "1.2.3.4"


def test_get_header_returns_none_when_missing() -> None:
	scope = {"headers": [(b"host", b"localhost")]}
	assert get_header(scope, b"x-request-id") is None


def test_get_header_returns_none_when_no_headers() -> None:
	scope: dict[str, object] = {}
	assert get_header(scope, b"x-request-id") is None


def test_get_client_ip_from_forwarded_header() -> None:
	scope = {"headers": [(b"x-forwarded-for", b"10.0.0.1, 192.168.1.1")]}
	assert get_client_ip(scope) == "10.0.0.1"


def test_get_client_ip_from_forwarded_header_single() -> None:
	scope = {"headers": [(b"x-forwarded-for", b"  203.0.113.50  ")]}
	assert get_client_ip(scope) == "203.0.113.50"


def test_get_client_ip_from_socket_client() -> None:
	scope = {"headers": [], "client": ("172.16.0.5", 54321)}
	assert get_client_ip(scope) == "172.16.0.5"


def test_get_client_ip_unknown_when_no_info() -> None:
	scope: dict[str, object] = {"headers": []}
	assert get_client_ip(scope) == "unknown"


def test_append_header_adds_to_message() -> None:
	message: dict[str, object] = {"type": "http.response.start", "headers": []}
	append_header(message, b"x-custom", "value123")
	headers = message["headers"]
	assert isinstance(headers, list)
	assert (b"x-custom", b"value123") in headers


def test_append_header_creates_headers_list_if_missing() -> None:
	message: dict[str, object] = {"type": "http.response.start"}
	append_header(message, b"x-test", "abc")
	assert (b"x-test", b"abc") in message["headers"]  # type: ignore[operator]


# -- rate limiter tests --


@pytest.mark.asyncio
async def test_rate_limiter_skipped_in_test_mode(client: AsyncClient) -> None:
	"""rate limiter must not block requests when TESTING=True."""
	for _ in range(5):
		resp = await client.get("/health")
		assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiter_exempt_paths() -> None:
	"""exempt paths should never be rate-limited, even with TESTING=False."""
	from api.boot_settings import boot_settings
	from api.main import app

	prev = boot_settings.TESTING
	boot_settings.TESTING = False
	try:
		async with AsyncClient(
			transport=ASGITransport(app=app),
			base_url="http://test",
		) as c:
			# health is exempt
			resp = await c.get("/health")
			assert resp.status_code == 200
			# root is exempt
			resp = await c.get("/")
			assert resp.status_code == 200
	finally:
		boot_settings.TESTING = prev


@pytest.mark.asyncio
async def test_rate_limiter_returns_429_when_exceeded() -> None:
	"""simulate exceeding the rate limit via mocked redis INCR."""
	from api.boot_settings import boot_settings
	from api.main import app

	prev = boot_settings.TESTING
	boot_settings.TESTING = False

	# mock redis to return a count above the limit
	mock_conn = AsyncMock()
	mock_conn.incrby = AsyncMock(return_value=9999)
	mock_conn.expire = AsyncMock()

	try:
		with patch("api.middleware.rate_limit.redis_client") as mock_rc:
			mock_rc.get.return_value = mock_conn
			async with AsyncClient(
				transport=ASGITransport(app=app),
				base_url="http://test",
			) as c:
				resp = await c.get("/v1/settings")
				assert resp.status_code == 429
				assert resp.json()["detail"] == "rate limit exceeded"
				assert "Retry-After" in resp.headers
	finally:
		boot_settings.TESTING = prev


@pytest.mark.asyncio
async def test_rate_limiter_fails_open_on_redis_error() -> None:
	"""if redis is unreachable, requests should pass through."""
	from api.boot_settings import boot_settings
	from api.main import app

	prev = boot_settings.TESTING
	boot_settings.TESTING = False

	try:
		with patch("api.middleware.rate_limit.redis_client") as mock_rc:
			mock_rc.get.side_effect = RuntimeError("not connected")
			async with AsyncClient(
				transport=ASGITransport(app=app),
				base_url="http://test",
			) as c:
				resp = await c.get("/v1/settings")
				# should not be 429 - request passes through
				assert resp.status_code != 429
	finally:
		boot_settings.TESTING = prev


@pytest.mark.asyncio
async def test_rate_limiter_uses_x_user_id_header() -> None:
	"""the limiter should key by x-user-id header when present."""
	from api.boot_settings import boot_settings
	from api.main import app

	prev = boot_settings.TESTING
	boot_settings.TESTING = False

	mock_conn = AsyncMock()
	mock_conn.incrby = AsyncMock(return_value=1)
	mock_conn.expire = AsyncMock()

	try:
		with patch("api.middleware.rate_limit.redis_client") as mock_rc:
			mock_rc.get.return_value = mock_conn
			async with AsyncClient(
				transport=ASGITransport(app=app),
				base_url="http://test",
			) as c:
				await c.get(
					"/v1/settings",
					headers={"X-User-Id": "user_abc"},
				)
				# verify the redis key contains the user id
				call_args = mock_conn.incrby.call_args
				assert call_args is not None
				key = call_args[0][0]
				assert "user_abc" in key
				assert key.startswith("nokodo-ai:rl:")
	finally:
		boot_settings.TESTING = prev


@pytest.mark.asyncio
async def test_rate_limiter_websocket_passthrough() -> None:
	"""websocket connections should not be rate-limited."""
	from api.middleware.rate_limit import RateLimitMiddleware

	called = False

	async def inner_app(scope: Scope, receive: Receive, send: Send) -> None:
		nonlocal called
		called = True

	async def receive() -> Message:
		return {"type": "websocket.disconnect"}

	async def send(message: Message) -> None:
		return None

	mw = RateLimitMiddleware(inner_app)
	scope: Scope = {"type": "websocket", "path": "/ws"}
	await mw(scope, receive, send)
	assert called is True
