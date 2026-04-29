"""cross-worker cache invalidation via redis pub/sub.

when a worker changes something that affects cached state (e.g. admin
updates the default embedding model or task model settings), it publishes
an invalidation signal. every worker subscribes to the channel and clears
the affected process-local caches.

usage::

    from api.redis.cache_invalidation import publish_invalidation

    # after admin changes embedding model settings
    await publish_invalidation("embedding_model")

    # after admin changes task model settings
    await publish_invalidation("task_models")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from redis.exceptions import RedisError

from api.redis.pubsub import PubSubChannel


logger = logging.getLogger(__name__)

_CHANNEL = PubSubChannel("nokodo_ai:cache:invalidate")

InvalidationHandler = Callable[[], None]

# registered invalidation handlers: signal_name -> list of callables
_handlers: dict[str, list[InvalidationHandler]] = {}


def on_invalidation(signal: str, handler: InvalidationHandler) -> None:
	"""register a handler to be called when a cache invalidation signal fires.

	handlers should be plain callables (sync). they are called in the
	subscriber task context.
	"""
	_handlers.setdefault(signal, []).append(handler)


async def publish_invalidation(signal: str) -> None:
	"""broadcast a cache invalidation signal to all workers."""
	try:
		await _CHANNEL.publish({"signal": signal})
	except (RedisError, OSError):
		logger.debug("failed to publish cache invalidation: %s", signal)


async def start_invalidation_subscriber() -> asyncio.Task[None]:
	"""start a background task that listens for invalidation signals."""

	async def _listener() -> None:
		backoff = 0.5
		max_backoff = 5.0
		while True:
			try:
				async for payload in _CHANNEL.subscribe():
					signal = payload.get("signal")
					if not signal or not isinstance(signal, str):
						continue
					handlers = _handlers.get(signal, [])
					for handler in handlers:
						try:
							handler()
						except Exception:
							logger.exception(
								"cache invalidation handler failed for %s",
								signal,
							)
				# subscribe() returned cleanly - rare; reconnect with reset.
				backoff = 0.5
			except asyncio.CancelledError:
				return
			except Exception:
				logger.exception(
					"cache invalidation subscriber crashed, reconnecting in %.1fs",
					backoff,
				)
				await asyncio.sleep(backoff)
				backoff = min(backoff * 2, max_backoff)

	task = asyncio.create_task(_listener(), name="cache-invalidation-subscriber")
	return task
