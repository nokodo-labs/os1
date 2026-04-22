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

from redis.exceptions import RedisError

from api.redis.pubsub import PubSubChannel


logger = logging.getLogger(__name__)

_CHANNEL = PubSubChannel("nokodo_ai:cache:invalidate")

# registered invalidation handlers: signal_name -> list of callables
_handlers: dict[str, list[object]] = {}


def on_invalidation(signal: str, handler: object) -> None:
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
		try:
			async for payload in _CHANNEL.subscribe():
				signal = payload.get("signal")
				if not signal or not isinstance(signal, str):
					continue
				handlers = _handlers.get(signal, [])
				for handler in handlers:
					try:
						handler()  # type: ignore[operator]
					except Exception:
						logger.exception(
							"cache invalidation handler failed for %s", signal
						)
		except asyncio.CancelledError:
			return
		except Exception:
			logger.exception("cache invalidation subscriber crashed")

	task = asyncio.create_task(_listener(), name="cache-invalidation-subscriber")
	return task
