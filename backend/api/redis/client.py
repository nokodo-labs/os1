"""singleton redis / valkey client.

the client is connected at app startup and closed at shutdown. redis is a
hard dependency: connection failures during boot abort startup so the
problem surfaces immediately rather than silently breaking cross-worker
features (steering bus, run sse fanout) at runtime.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import Final, cast

import redis.asyncio as redis_async
from redis.asyncio import Redis

from api.settings import settings


logger = logging.getLogger(__name__)


# small, predictable pool. the api is mostly bound by db / model latency,
# and redis ops are sub-ms; we don't need a large pool.
_DEFAULT_MAX_CONNECTIONS: Final[int] = 32

# redis ops should be near-instant on healthy infra. surface stalls quickly
# rather than letting requests hang.
_DEFAULT_SOCKET_TIMEOUT_S: Final[float] = 2.0
_DEFAULT_SOCKET_CONNECT_TIMEOUT_S: Final[float] = 2.0


class RedisClient:
	"""lifecycle-managed redis connection holder.

	minimal by design - higher-level primitives (pub/sub, streams, locks)
	live in dedicated modules so the client stays a thin connection manager.

	exposes two pools:

	- ``get()`` - request-response commands, with ``socket_timeout`` for
		fast failure on stalled ops.
	- ``get_pubsub()`` - long-lived blocking readers (pub/sub). no
		``socket_timeout`` because ``listen()`` blocks until a message
		arrives; a 2s ceiling would kill it.
	"""

	def __init__(self) -> None:
		self._conn: Redis | None = None
		self._pubsub_conn: Redis | None = None
		self._url: str | None = None

	@property
	def url(self) -> str | None:
		"""the configured redis url, if any."""
		return self._url

	async def connect(
		self,
		url: str | None = None,
		max_connections: int = _DEFAULT_MAX_CONNECTIONS,
	) -> None:
		"""open the connection pool and verify reachability.

		idempotent: a second call is a no-op while connected. raises on
		connection failure - redis is required and there is no fallback.
		"""
		if self._conn is not None:
			return
		target_url = url or settings.cache.redis.url
		conn = redis_async.from_url(
			target_url,
			max_connections=max_connections,
			socket_timeout=_DEFAULT_SOCKET_TIMEOUT_S,
			socket_connect_timeout=_DEFAULT_SOCKET_CONNECT_TIMEOUT_S,
			decode_responses=False,
			health_check_interval=30,
			client_name=settings.cache.redis.client_name,
		)
		# separate pool for pub/sub: no socket_timeout so listen() can
		# block indefinitely waiting for messages.
		pubsub_conn = redis_async.from_url(
			target_url,
			max_connections=max_connections,
			socket_connect_timeout=_DEFAULT_SOCKET_CONNECT_TIMEOUT_S,
			decode_responses=False,
			client_name=settings.cache.redis.client_name,
		)
		# TODO(observability): once OpenTelemetry is wired up, add
		# opentelemetry-instrumentation-redis to instrument every op
		# with spans + metrics.
		# redis-py types ``ping`` as a union of sync/async to share the
		# class hierarchy; the async client always returns an awaitable.
		await cast("Awaitable[bool]", conn.ping())
		self._conn = conn
		self._pubsub_conn = pubsub_conn
		self._url = target_url
		logger.info("redis connected at %s", target_url)

	async def aclose(self) -> None:
		"""close the connection pool. idempotent."""
		if self._conn is None:
			return
		conn = self._conn
		pubsub_conn = self._pubsub_conn
		self._conn = None
		self._pubsub_conn = None
		self._url = None
		await conn.aclose()
		if pubsub_conn is not None:
			await pubsub_conn.aclose()

	def get(self) -> Redis:
		"""return the live redis connection.

		raises ``RuntimeError`` if called before ``connect()`` or after
		``aclose()``.
		"""
		if self._conn is None:
			raise RuntimeError(
				"redis client is not connected; call connect() during app startup"
			)
		return self._conn

	def get_pubsub(self) -> Redis:
		"""return a redis client for pub/sub use (no socket_timeout)."""
		if self._pubsub_conn is None:
			raise RuntimeError(
				"redis client is not connected; call connect() during app startup"
			)
		return self._pubsub_conn


redis_client = RedisClient()
