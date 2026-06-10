"""sliding-window rate limiter backed by redis.

uses a simple INCR + EXPIRE pattern per (user-id or client-ip) per
minute bucket. when the limit is exceeded a 429 response is returned
immediately without touching the application layer.

the limit is read from ``settings.limits.rate_limit_requests_per_minute``
at request time, so admin changes take effect without restart.

websocket upgrades and health endpoints are exempt.
"""

from __future__ import annotations

import time

from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.boot_settings import boot_settings
from api.redis import redis_client
from api.settings import settings

from ._utils import get_client_ip, get_header


_EXEMPT_PATHS = frozenset({"/health", "/", "/v1/docs", "/v1/redoc", "/v1/openapi.json"})

# methods that do not count (preflight / metadata)
_EXEMPT_METHODS = frozenset({"OPTIONS", "HEAD"})

# heavier write methods consume extra quota units
_METHOD_WEIGHT: dict[str, int] = {
	"POST": 5,
	"PUT": 4,
	"PATCH": 3,
	"DELETE": 3,
}
_DEFAULT_WEIGHT = 1


class RateLimitMiddleware:
	"""per-user sliding-window rate limiter."""

	__slots__ = ("app",)

	def __init__(self, app: ASGIApp) -> None:
		self.app = app

	async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
		if scope["type"] != "http":
			await self.app(scope, receive, send)
			return

		path: str = scope.get("path", "")
		method: str = scope.get("method", "GET").upper()

		if path in _EXEMPT_PATHS or method in _EXEMPT_METHODS:
			await self.app(scope, receive, send)
			return

		if boot_settings.TESTING:
			await self.app(scope, receive, send)
			return

		# identify the caller - prefer authenticated user id, fall back to ip
		identity = get_header(scope, b"x-user-id") or get_client_ip(scope)
		minute_bucket = int(time.time()) // 60

		try:
			conn = redis_client.get()
			rkey = f"nokodo-ai:rl:{identity}:{minute_bucket}"
			weight = _METHOD_WEIGHT.get(method, _DEFAULT_WEIGHT)
			count = await conn.incrby(rkey, weight)
			if count == weight:
				await conn.expire(rkey, 120)
		except RedisError, OSError, RuntimeError:
			# redis down - fail open to avoid blocking all traffic
			await self.app(scope, receive, send)
			return

		limit = settings.limits.rate_limit_requests_per_minute
		if count > limit:
			response = JSONResponse(
				{"detail": "rate limit exceeded"},
				status_code=429,
				headers={"Retry-After": str(60 - (int(time.time()) % 60))},
			)
			await response(scope, receive, send)
			return

		await self.app(scope, receive, send)
