"""tests for async concurrency helpers."""

import asyncio

import pytest

from nokodo_ai.utils.concurrency import gather_bounded, map_concurrently


async def test_gather_bounded_preserves_input_order() -> None:
	"""results follow input order even when later items finish first."""

	async def echo(value: int, delay: float) -> int:
		await asyncio.sleep(delay)
		return value

	results = await gather_bounded([echo(0, 0.03), echo(1, 0.02), echo(2, 0.01)])
	assert results == [0, 1, 2]


async def test_gather_bounded_empty_returns_empty() -> None:
	assert await gather_bounded([]) == []


async def test_gather_bounded_default_caps_at_100() -> None:
	"""with no explicit limit, at most DEFAULT_CONCURRENCY run at once."""
	active = 0
	peak = 0

	async def track() -> None:
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		await asyncio.sleep(0.02)
		active -= 1

	await gather_bounded(track() for _ in range(150))
	assert peak == 100


async def test_gather_bounded_limit_none_is_unbounded() -> None:
	"""limit=None opts out of the cap - every awaitable runs at once."""
	active = 0
	peak = 0

	async def track() -> None:
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		await asyncio.sleep(0.02)
		active -= 1

	await gather_bounded((track() for _ in range(150)), limit=None)
	assert peak == 150


async def test_gather_bounded_respects_limit() -> None:
	"""no more than `limit` awaitables run at the same time."""
	active = 0
	peak = 0

	async def track() -> None:
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		await asyncio.sleep(0.02)
		active -= 1

	await gather_bounded((track() for _ in range(20)), limit=4)
	assert peak == 4


async def test_gather_bounded_returns_exceptions_in_place() -> None:
	async def ok() -> int:
		return 7

	async def boom() -> int:
		raise ValueError("boom")

	results = await gather_bounded([ok(), boom()], limit=None, return_exceptions=True)
	assert results[0] == 7
	assert isinstance(results[1], ValueError)


async def test_gather_bounded_propagates_by_default() -> None:
	async def boom() -> int:
		raise ValueError("boom")

	with pytest.raises(ValueError):
		await gather_bounded([boom()])


async def test_map_concurrently_preserves_order_and_bounds() -> None:
	active = 0
	peak = 0

	async def square(value: int) -> int:
		nonlocal active, peak
		active += 1
		peak = max(peak, active)
		await asyncio.sleep(0.02)
		active -= 1
		return value * value

	results = await map_concurrently(square, range(10), limit=3)
	assert results == [value * value for value in range(10)]
	assert peak == 3
