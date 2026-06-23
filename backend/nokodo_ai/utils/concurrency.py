"""async concurrency helpers for bounded fan-out of awaitable work.

asyncio.gather already runs awaitables concurrently and preserves order, but
it has no built-in ceiling: handed thousands of awaitables it launches them
all at once. unlike a thread pool the limit is not CPU count - it is remote
rate limits, connection-pool sizes and memory. these helpers add that missing
ceiling (a semaphore) and default to a conservative cap so a large fan-out
never floods a provider, the database or the OWUI deployment by accident.
pass limit=None to opt into fully unbounded fan-out (plain asyncio.gather).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Literal, overload


# default in-flight ceiling for the helpers below. chosen to be generous for
# fast local work while still capping pathological fan-outs. callers that talk
# to a rate-limited provider should pass a smaller limit explicitly.
DEFAULT_CONCURRENCY = 100


@overload
async def gather_bounded[ResultT](
	awaitables: Iterable[Awaitable[ResultT]],
	limit: int | None = ...,
	return_exceptions: Literal[False] = ...,
) -> list[ResultT]: ...


@overload
async def gather_bounded[ResultT](
	awaitables: Iterable[Awaitable[ResultT]],
	limit: int | None,
	return_exceptions: Literal[True],
) -> list[ResultT | BaseException]: ...


async def gather_bounded[ResultT](
	awaitables: Iterable[Awaitable[ResultT]],
	limit: int | None = DEFAULT_CONCURRENCY,
	return_exceptions: bool = False,
) -> list[ResultT] | list[ResultT | BaseException]:
	"""run awaitables concurrently, capped at `limit`, ordered by input.

	`limit` caps how many run at once and defaults to DEFAULT_CONCURRENCY.
	pass limit=None (or a value <= 0) to run every awaitable at once with no
	cap - equivalent to a bare asyncio.gather. results keep the order of
	`awaitables` regardless of completion order, so they can be zipped back
	against their inputs.

	when `return_exceptions` is True, exceptions are returned in place of
	results instead of propagating - same semantics as asyncio.gather. the
	typed overloads require `limit` alongside it (e.g.
	`gather_bounded(coros, limit=None, return_exceptions=True)`) so a bare
	`True` can never bind positionally to `limit` (bool is an int subtype).
	"""
	items = list(awaitables)
	if not items:
		return []
	if limit is None or limit <= 0 or limit >= len(items):
		return list(await asyncio.gather(*items, return_exceptions=return_exceptions))

	semaphore = asyncio.Semaphore(limit)

	async def _run(awaitable: Awaitable[ResultT]) -> ResultT:
		async with semaphore:
			return await awaitable

	return list(
		await asyncio.gather(
			*(_run(item) for item in items),
			return_exceptions=return_exceptions,
		)
	)


@overload
async def map_concurrently[ItemT, ResultT](
	func: Callable[[ItemT], Awaitable[ResultT]],
	items: Iterable[ItemT],
	limit: int | None = ...,
	return_exceptions: Literal[False] = ...,
) -> list[ResultT]: ...


@overload
async def map_concurrently[ItemT, ResultT](
	func: Callable[[ItemT], Awaitable[ResultT]],
	items: Iterable[ItemT],
	limit: int | None,
	return_exceptions: Literal[True],
) -> list[ResultT | BaseException]: ...


async def map_concurrently[ItemT, ResultT](
	func: Callable[[ItemT], Awaitable[ResultT]],
	items: Iterable[ItemT],
	limit: int | None = DEFAULT_CONCURRENCY,
	return_exceptions: bool = False,
) -> list[ResultT] | list[ResultT | BaseException]:
	"""apply an async `func` to each item concurrently, preserving order.

	thin wrapper over `gather_bounded` for the common case of mapping one
	coroutine function across a collection. see `gather_bounded` for the
	`limit` and `return_exceptions` semantics.
	"""
	awaitables = (func(item) for item in items)
	if return_exceptions:
		return await gather_bounded(awaitables, limit, return_exceptions=True)
	return await gather_bounded(awaitables, limit)
