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

import json
import logging
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

from api.redis.client import redis_client


logger = logging.getLogger(__name__)

_PREFIX = "nokodo-ai:cache:"
_TAG_PREFIX = "nokodo-ai:tag:"


class RedisCache:
	"""thin typed cache over the singleton redis connection."""

	def _conn(self) -> Redis:
		return redis_client.get()

	async def get(self, key: str) -> object | None:
		"""fetch a cached value. returns None on miss or redis error"""
		try:
			raw = await self._conn().get(f"{_PREFIX}{key}")
		except RedisError, OSError:
			return None
		except RuntimeError as exc:
			logger.warning("cache get skipped for %s: %s", key, exc)
			return None
		if raw is None:
			return None
		try:
			decoded: object = json.loads(raw)
		except json.JSONDecodeError, TypeError:
			return None
		return decoded

	async def get_many(self, keys: list[str]) -> list[object | None]:
		"""fetch several cached values in one Redis round trip."""
		if not keys:
			return []
		try:
			raw_values = await self._conn().mget([f"{_PREFIX}{key}" for key in keys])
		except RedisError, OSError:
			return [None] * len(keys)
		except RuntimeError as exc:
			logger.warning("cache multi-get skipped: %s", exc)
			return [None] * len(keys)
		values: list[object | None] = []
		for raw in raw_values:
			if raw is None:
				values.append(None)
				continue
			try:
				values.append(json.loads(raw))
			except json.JSONDecodeError, TypeError:
				values.append(None)
		return values

	async def set(
		self,
		key: str,
		value: object,
		ttl: int = 60,
		tags: list[str] | None = None,
		nx: bool = False,
	) -> bool:
		"""store a JSON-serializable value with optional tags.

		``ttl`` is in seconds. tags enable group invalidation. ``nx`` only
		writes when the key is absent, so racing cache fills cannot clobber
		an authoritative write-through.

		returns False when the write failed. a failed FILL is harmless - the
		caller already holds the freshly resolved answer. a failed
		INVALIDATION is not: this layer reports the failure and the caller
		decides, and callers whose entries gate authorization must retry
		until the write lands rather than proceed (see
		``authorization.cache._increment_versions_until_written``).
		"""
		full_key = f"{_PREFIX}{key}"
		try:
			conn = self._conn()
			if tags:
				# single transaction: a fault between the value write and the tag
				# registration would hide the entry from tag invalidation until its TTL.
				pipe = conn.pipeline(transaction=True)
				pipe.set(full_key, json.dumps(value), ex=ttl, nx=nx)
				for tag in tags:
					pipe.sadd(f"{_TAG_PREFIX}{tag}", full_key)
					pipe.expire(f"{_TAG_PREFIX}{tag}", ttl + 60)
				await pipe.execute()
			else:
				await conn.set(full_key, json.dumps(value), ex=ttl, nx=nx)
		except RedisError, OSError:
			logger.debug("cache set failed for %s", key)
			return False
		except RuntimeError as exc:
			logger.warning("cache set skipped for %s: %s", key, exc)
			return False
		return True

	async def delete(self, key: str) -> bool:
		"""remove a single cache entry.

		returns False when the delete failed (fail-open), so
		security-critical callers can escalate.
		"""
		try:
			await self._conn().delete(f"{_PREFIX}{key}")
		except RedisError, OSError:
			return False
		except RuntimeError as exc:
			logger.warning("cache delete skipped for %s: %s", key, exc)
			return False
		return True

	async def increment(self, key: str) -> int | None:
		"""atomically increment an integer cache value.

		returns the new value, or None when redis is unavailable.
		"""
		try:
			return int(await self._conn().incr(f"{_PREFIX}{key}"))
		except RedisError, OSError:
			logger.debug("cache increment failed for %s", key)
			return None
		except RuntimeError as exc:
			logger.warning("cache increment skipped for %s: %s", key, exc)
			return None

	async def increment_many(self, keys: list[str]) -> bool:
		"""atomically increment several integer cache values."""
		if not keys:
			return True
		try:
			pipe = self._conn().pipeline(transaction=True)
			for key in dict.fromkeys(keys):
				pipe.incr(f"{_PREFIX}{key}")
			await pipe.execute()
		except RedisError, OSError:
			logger.debug("cache multi-increment failed")
			return False
		except RuntimeError as exc:
			logger.warning("cache multi-increment skipped: %s", exc)
			return False
		return True

	async def invalidate_tag(self, tag: str) -> bool:
		"""delete all cache entries associated with a tag.

		returns False when the invalidation failed (fail-open), so
		security-critical callers can escalate.
		"""
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
		except RedisError, OSError:
			logger.debug("cache invalidate_tag failed for %s", tag)
			return False
		except RuntimeError as exc:
			logger.warning("cache invalidate_tag skipped for %s: %s", tag, exc)
			return False
		return True

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
