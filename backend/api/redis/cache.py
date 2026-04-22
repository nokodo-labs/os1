"""redis-backed cache with tag-based invalidation.

provides a thin, typed caching layer over the singleton redis client.
keys are namespaced with a prefix so they don't collide with pub/sub or
other redis data. values are JSON-serialized.

tag-based invalidation: every cached entry can be associated with one or
more tags (e.g. ``thread:{id}``, ``user:{id}``). invalidating a tag
atomically deletes all entries tagged with it.

usage::

    from api.redis.cache import cache

    # simple get/set
    await cache.set("principal:user_123", data, ttl=60)
    result = await cache.get("principal:user_123")

    # with tags for invalidation
    await cache.set(
        "access:thread_abc:user_123",
        level,
        ttl=60,
        tags=["thread:thread_abc", "user:user_123"],
    )
    # invalidate all entries tagged with a specific thread
    await cache.invalidate_tag("thread:thread_abc")
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from api.redis.client import redis_client


logger = logging.getLogger(__name__)

_PREFIX = "nokodo_ai:cache:"
_TAG_PREFIX = "nokodo_ai:tag:"


class RedisCache:
	"""thin typed cache over the singleton redis connection."""

	def _conn(self) -> Redis:
		return redis_client.get()

	async def get(self, key: str) -> object | None:
		"""fetch a cached value. returns None on miss or redis error."""
		try:
			raw = await self._conn().get(f"{_PREFIX}{key}")
		except (RedisError, OSError):
			return None
		if raw is None:
			return None
		try:
			return json.loads(raw)
		except (json.JSONDecodeError, TypeError):
			return None

	async def set(
		self,
		key: str,
		value: object,
		ttl: int = 60,
		tags: list[str] | None = None,
	) -> None:
		"""store a JSON-serializable value with optional tags.

		``ttl`` is in seconds. tags enable group invalidation.
		"""
		full_key = f"{_PREFIX}{key}"
		try:
			conn = self._conn()
			await conn.set(full_key, json.dumps(value), ex=ttl)
			if tags:
				pipe = conn.pipeline(transaction=False)
				for tag in tags:
					tag_key = f"{_TAG_PREFIX}{tag}"
					pipe.sadd(tag_key, full_key)
					pipe.expire(tag_key, ttl + 60)
				await pipe.execute()
		except (RedisError, OSError):
			logger.debug("cache set failed for %s", key)

	async def delete(self, key: str) -> None:
		"""remove a single cache entry."""
		try:
			await self._conn().delete(f"{_PREFIX}{key}")
		except (RedisError, OSError):
			pass

	async def invalidate_tag(self, tag: str) -> None:
		"""delete all cache entries associated with a tag."""
		tag_key = f"{_TAG_PREFIX}{tag}"
		try:
			conn = self._conn()
			# collect tagged keys via SSCAN to avoid smembers typing issue
			tagged_keys: list[bytes] = []
			cursor: int = 0
			while True:
				cursor, batch = await conn.sscan(tag_key, cursor=cursor)
				tagged_keys.extend(batch)
				if cursor == 0:
					break
			if tagged_keys:
				pipe = conn.pipeline(transaction=False)
				for member in tagged_keys:
					pipe.delete(member)
				pipe.delete(tag_key)
				await pipe.execute()
			else:
				await conn.delete(tag_key)
		except (RedisError, OSError):
			logger.debug("cache invalidate_tag failed for %s", tag)

	async def get_or_set(
		self,
		key: str,
		factory: Callable[[], Awaitable[object]],
		ttl: int = 60,
		tags: list[str] | None = None,
	) -> object:
		"""return cached value or call factory, cache the result, and return it."""
		cached = await self.get(key)
		if cached is not None:
			return cached
		result = await factory()
		await self.set(key, result, ttl=ttl, tags=tags)
		return result


cache = RedisCache()
