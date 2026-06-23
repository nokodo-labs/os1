"""tests for redis cache and cache invalidation modules."""

from __future__ import annotations

import asyncio

import pytest

from api.redis import (
	cache,
	on_invalidation,
	publish_invalidation,
	start_invalidation_subscriber,
)


# -- RedisCache tests --


@pytest.mark.asyncio
async def test_cache_get_miss_returns_none() -> None:
	result = await cache.get("nonexistent_key_xyz")
	assert result is None


@pytest.mark.asyncio
async def test_cache_set_and_get() -> None:
	await cache.set("test:simple", {"hello": "world"}, ttl=10)
	result = await cache.get("test:simple")
	assert result == {"hello": "world"}
	await cache.delete("test:simple")


@pytest.mark.asyncio
async def test_cache_set_with_tags_and_invalidate() -> None:
	await cache.set("test:tagged1", "val1", ttl=10, tags=["test:group_a"])
	await cache.set("test:tagged2", "val2", ttl=10, tags=["test:group_a"])
	await cache.set("test:tagged3", "val3", ttl=10, tags=["test:group_b"])

	assert await cache.get("test:tagged1") == "val1"
	assert await cache.get("test:tagged2") == "val2"
	assert await cache.get("test:tagged3") == "val3"

	# invalidating group_a should remove tagged1 and tagged2
	await cache.invalidate_tag("test:group_a")
	assert await cache.get("test:tagged1") is None
	assert await cache.get("test:tagged2") is None
	# group_b should be untouched
	assert await cache.get("test:tagged3") == "val3"

	await cache.invalidate_tag("test:group_b")
	await cache.delete("test:tagged3")


@pytest.mark.asyncio
async def test_cache_delete() -> None:
	await cache.set("test:del", 42, ttl=10)
	assert await cache.get("test:del") == 42
	await cache.delete("test:del")
	assert await cache.get("test:del") is None


@pytest.mark.asyncio
async def test_cache_invalidate_nonexistent_tag() -> None:
	# should not raise
	await cache.invalidate_tag("test:no_such_tag")


@pytest.mark.asyncio
async def test_cache_get_or_set_populates_on_miss() -> None:
	await cache.delete("test:getorset")

	async def factory() -> list[int]:
		return [1, 2, 3]

	result = await cache.get_or_set("test:getorset", factory, ttl=10)
	assert result == [1, 2, 3]

	# second call should return cached value without calling factory
	call_count = 0

	async def counting_factory() -> list[int]:
		nonlocal call_count
		call_count += 1
		return [4, 5, 6]

	result2 = await cache.get_or_set("test:getorset", counting_factory, ttl=10)
	assert result2 == [1, 2, 3]
	assert call_count == 0

	await cache.delete("test:getorset")


@pytest.mark.asyncio
async def test_cache_stores_lists_of_strings() -> None:
	"""verify caching user id lists (the main use case)."""
	ids = ["user_abc", "user_def", "user_ghi"]
	await cache.set("test:userids", ids, ttl=10, tags=["test:resource_x"])
	result = await cache.get("test:userids")
	assert result == ids
	await cache.invalidate_tag("test:resource_x")
	assert await cache.get("test:userids") is None


# -- cache invalidation pub/sub tests --


@pytest.mark.asyncio
async def test_invalidation_pubsub_fires_handler() -> None:
	"""publish_invalidation should trigger registered handlers."""
	fired: list[str] = []

	def handler() -> None:
		fired.append("called")

	on_invalidation("test_signal", handler)
	task = await start_invalidation_subscriber()

	# give subscriber time to attach
	await asyncio.sleep(0.1)

	await publish_invalidation("test_signal")

	# give the message time to propagate
	await asyncio.sleep(0.3)

	task.cancel()
	try:
		await task
	except asyncio.CancelledError:
		pass

	assert len(fired) >= 1
