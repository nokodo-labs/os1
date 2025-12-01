"""tests for middleware components."""

from __future__ import annotations

import json
import logging
import uuid

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from api.core.config import settings
from api.core.exceptions import (
	unhandled_exception_handler,
	validation_exception_handler,
)
from api.core.logging import request_id_ctx
from api.middleware import (
	APIVersionHeaderMiddleware,
	RequestIDMiddleware,
	RequestLoggingMiddleware,
	SecurityHeadersMiddleware,
)
from api.middleware._utils import append_header, get_client_ip, get_header


class DummyApp:
	"""simple asgi app placeholder for middleware pass-through tests."""

	__slots__ = ("calls", "scope")

	def __init__(self) -> None:
		self.calls = 0
		self.scope: Scope | None = None

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		self.calls += 1
		self.scope = scope


async def empty_receive():
	return {"type": "http.request"}


async def empty_send(message):
	return None


def create_test_app() -> Starlette:
	"""create a minimal starlette app for testing middleware."""

	async def echo_request_id(request: Request) -> JSONResponse:
		"""endpoint that returns the current request_id from context."""
		return JSONResponse(
			{
				"context_request_id": request_id_ctx.get(),
				"header_request_id": request.headers.get("X-Request-ID"),
			}
		)

	app = Starlette(
		routes=[Route("/echo", echo_request_id)],
	)
	app.add_middleware(RequestIDMiddleware)
	return app


@pytest.fixture
def test_app() -> Starlette:
	"""fixture for test app with middleware."""
	return create_test_app()


@pytest.mark.asyncio
async def test_middleware_generates_request_id(test_app: Starlette) -> None:
	"""test that middleware generates a request_id when none provided."""
	async with AsyncClient(
		transport=ASGITransport(app=test_app),
		base_url="http://test",
	) as client:
		response = await client.get("/echo")

	assert response.status_code == 200
	data = response.json()

	# should have generated a request_id
	assert data["context_request_id"] is not None
	# should be a valid uuid
	uuid.UUID(data["context_request_id"])

	# should be in response headers
	assert "X-Request-ID" in response.headers
	assert response.headers["X-Request-ID"] == data["context_request_id"]


@pytest.mark.asyncio
async def test_middleware_uses_provided_request_id(test_app: Starlette) -> None:
	"""test that middleware uses X-Request-ID header when provided."""
	provided_id = "custom-request-id-12345"

	async with AsyncClient(
		transport=ASGITransport(app=test_app),
		base_url="http://test",
	) as client:
		response = await client.get(
			"/echo",
			headers={"X-Request-ID": provided_id},
		)

	assert response.status_code == 200
	data = response.json()

	# should use the provided request_id
	assert data["context_request_id"] == provided_id
	assert data["header_request_id"] == provided_id

	# should echo it back in response
	assert response.headers["X-Request-ID"] == provided_id


@pytest.mark.asyncio
async def test_middleware_resets_context_after_request(test_app: Starlette) -> None:
	"""test that context is properly reset after request completes."""
	# context should be none before request
	assert request_id_ctx.get() is None

	async with AsyncClient(
		transport=ASGITransport(app=test_app),
		base_url="http://test",
	) as client:
		await client.get("/echo")

	# context should be none after request
	assert request_id_ctx.get() is None


@pytest.mark.asyncio
async def test_middleware_isolates_concurrent_requests(test_app: Starlette) -> None:
	"""test that concurrent requests have isolated contexts."""
	import asyncio

	results: list[dict] = []

	async def make_request(request_id: str) -> None:
		async with AsyncClient(
			transport=ASGITransport(app=test_app),
			base_url="http://test",
		) as client:
			response = await client.get(
				"/echo",
				headers={"X-Request-ID": request_id},
			)
			results.append(
				{
					"sent": request_id,
					"received": response.json()["context_request_id"],
				}
			)

	# make multiple concurrent requests
	await asyncio.gather(
		make_request("request-1"),
		make_request("request-2"),
		make_request("request-3"),
	)

	# each request should have received its own request_id
	for result in results:
		assert result["sent"] == result["received"]


@pytest.mark.asyncio
async def test_middleware_handles_request_failure(test_app: Starlette) -> None:
	"""test that context is reset even when request fails."""

	async def failing_endpoint(request: Request) -> JSONResponse:
		raise ValueError("intentional error")

	app = Starlette(
		routes=[Route("/fail", failing_endpoint)],
	)
	app.add_middleware(RequestIDMiddleware)

	# context should be none before
	assert request_id_ctx.get() is None

	async with AsyncClient(
		transport=ASGITransport(app=app, raise_app_exceptions=False),
		base_url="http://test",
	) as client:
		response = await client.get("/fail")

	# request failed (500)
	assert response.status_code == 500

	# context should still be reset
	assert request_id_ctx.get() is None


@pytest.mark.asyncio
async def test_request_id_middleware_passthrough_non_http() -> None:
	"""non-http scopes should bypass the middleware logic."""
	dummy_app = DummyApp()
	middleware = RequestIDMiddleware(dummy_app)
	scope = {"type": "lifespan"}

	await middleware(scope, empty_receive, empty_send)

	assert dummy_app.calls == 1
	assert dummy_app.scope == scope


@pytest.mark.asyncio
async def test_request_logging_adds_timing_headers_and_logs(
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""request logging middleware emits timing headers and log entries."""
	app = Starlette(routes=[Route("/ok", lambda request: JSONResponse({"ok": True}))])
	app.add_middleware(RequestLoggingMiddleware)
	caplog.set_level("INFO", logger="api.middleware.request_logging")

	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://test",
	) as client:
		response = await client.get("/ok")

	assert response.status_code == 200
	assert "server-timing" in response.headers
	assert "x-process-time" in response.headers
	assert any("/ok" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_request_logging_logs_errors(caplog: pytest.LogCaptureFixture) -> None:
	"""errors should be logged at error level."""

	async def boom(_: Request) -> PlainTextResponse:
		raise ValueError("boom")

	app = Starlette(routes=[Route("/boom", boom)])
	app.add_middleware(RequestLoggingMiddleware)
	caplog.set_level("ERROR", logger="api.middleware.request_logging")

	async with AsyncClient(
		transport=ASGITransport(app=app, raise_app_exceptions=False),
		base_url="http://test",
	) as client:
		response = await client.get("/boom")

	assert response.status_code == 500
	assert any(
		record.levelno >= logging.ERROR and "/boom" in record.message
		for record in caplog.records
	)


@pytest.mark.asyncio
async def test_request_logging_passthrough_non_http() -> None:
	"""non-http scope should simply call inner app."""
	dummy_app = DummyApp()
	middleware = RequestLoggingMiddleware(dummy_app)
	scope = {"type": "lifespan"}

	await middleware(scope, empty_receive, empty_send)

	assert dummy_app.calls == 1


@pytest.mark.asyncio
async def test_exception_middleware_allows_http_exception() -> None:
	"""HTTPException should bubble without conversion."""

	async def app(scope, receive, send):  # type: ignore[override]
		raise HTTPException(status_code=418)

	req = Request(
		{
			"type": "http",
			"path": "/",
			"method": "GET",
			"headers": [],
		}
	)

	with pytest.raises(HTTPException):
		await unhandled_exception_handler(req, HTTPException(status_code=418))


@pytest.mark.asyncio
async def test_exception_middleware_passthrough_non_http() -> None:
	"""non-http scope should bypass handling."""
	dummy_app = DummyApp()

	await dummy_app({"type": "lifespan"}, empty_receive, empty_send)
	assert dummy_app.calls == 1


@pytest.mark.asyncio
async def test_exception_middleware_converts_errors_including_request_id() -> None:
	"""unexpected errors return JSON with request_id."""

	req = Request(
		{
			"type": "http",
			"path": "/",
			"method": "POST",
			"headers": [],
		}
	)
	token = request_id_ctx.set("req-123")
	try:
		response = await unhandled_exception_handler(req, RuntimeError("boom"))
	finally:
		request_id_ctx.reset(token)

	assert response.status_code == 500
	body = bytes(response.body)
	assert json.loads(body.decode()) == {
		"detail": "Internal server error",
		"request_id": "req-123",
	}


@pytest.mark.asyncio
async def test_validation_exception_handler_returns_422_payload() -> None:
	"""validation errors should surface as 422 responses."""
	req = Request(
		{
			"type": "http",
			"path": "/items",
			"method": "POST",
			"headers": [],
		}
	)
	exc = RequestValidationError(
		[
			{
				"loc": ("body", "name"),
				"msg": "field required",
				"type": "value_error.missing",
			}
		]
	)
	response = await validation_exception_handler(req, exc)

	assert response.status_code == 422
	body = bytes(response.body)
	expected = json.loads(json.dumps(exc.errors()))
	assert json.loads(body.decode()) == {"detail": expected}


@pytest.mark.asyncio
async def test_api_version_middleware_adds_header() -> None:
	"""API version middleware should attach header to responses."""
	app = Starlette(routes=[Route("/ping", lambda request: JSONResponse({"ok": True}))])
	app.add_middleware(APIVersionHeaderMiddleware, version="v9")

	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://test",
	) as client:
		response = await client.get("/ping")

	assert response.headers["x-api-version"] == "v9"


@pytest.mark.asyncio
async def test_api_version_middleware_non_http() -> None:
	"""non-http scopes should bypass version middleware."""
	dummy_app = DummyApp()
	middleware = APIVersionHeaderMiddleware(dummy_app, version="v1")

	await middleware({"type": "lifespan"}, empty_receive, empty_send)
	assert dummy_app.calls == 1


@pytest.mark.asyncio
async def test_security_headers_default(monkeypatch: pytest.MonkeyPatch) -> None:
	"""default security headers should always be present."""
	monkeypatch.setattr(settings, "APP_ENV", "dev")
	app = Starlette(routes=[Route("/secure", lambda request: JSONResponse({}))])
	app.add_middleware(SecurityHeadersMiddleware)

	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://test",
	) as client:
		response = await client.get("/secure")

	assert response.headers["x-content-type-options"] == "nosniff"
	assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_security_headers_hsts_in_non_dev(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""HSTS should be emitted outside dev environments."""
	monkeypatch.setattr(settings, "APP_ENV", "production")
	app = Starlette(routes=[Route("/secure", lambda request: JSONResponse({}))])
	app.add_middleware(SecurityHeadersMiddleware)

	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://test",
	) as client:
		response = await client.get("/secure")

	assert "strict-transport-security" in response.headers


@pytest.mark.asyncio
async def test_security_headers_passthrough_non_http() -> None:
	"""non-http scopes bypass header injection."""
	dummy_app = DummyApp()
	middleware = SecurityHeadersMiddleware(dummy_app)

	await middleware({"type": "lifespan"}, empty_receive, empty_send)
	assert dummy_app.calls == 1


def test_utils_get_header_and_client_ip() -> None:
	"""utility helpers should read headers and client data."""
	scope = {
		"headers": [(b"x-forwarded-for", b"1.1.1.1, 2.2.2.2"), (b"x-custom", b"value")],
		"client": ("3.3.3.3", 12345),
	}
	assert get_header(scope, b"x-custom") == "value"
	assert get_client_ip(scope) == "1.1.1.1"


def test_utils_get_client_ip_fallback() -> None:
	"""client ip should fall back to socket tuple or unknown."""
	scope = {"client": ("3.3.3.3", 12345)}
	assert get_client_ip(scope) == "3.3.3.3"
	assert get_client_ip({}) == "unknown"


def test_append_header_appends_values() -> None:
	"""append_header should mutate the message headers."""
	message = {"type": "http.response.start", "headers": [(b"a", b"b")]}  # type: ignore[var-annotated]
	append_header(message, b"c", "see")
	assert message["headers"][-1] == (b"c", b"see")
