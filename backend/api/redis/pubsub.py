"""typed pub/sub helpers for cross-worker fanout.

design:

- ``PubSubChannel`` wraps a single redis pub/sub channel name and provides
  ``publish(payload)`` (json-encoded) and ``subscribe()`` (async iterator
  yielding decoded payloads) without callers ever touching raw bytes.
- the iterator is a true async generator, cancel-safe, and unsubscribes /
  closes the underlying connection in its ``finally:`` so leaked
  subscriptions don't pile up.
- ``payload`` is constrained to JSON-serializable mappings - this is the
  only contract callers need to honor.

intentionally NOT included here:

- per-pattern subscription / glob channels: the steering and run buses both
  key by a single id (run_id) so plain channels are sufficient.
- redis streams (``XADD`` / ``XREADGROUP``): we want push semantics, not
  consumer-group fan-in. add a ``StreamChannel`` later if a feature actually
  needs durable replay.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from redis.exceptions import RedisError

from api.redis.client import redis_client


logger = logging.getLogger(__name__)


class PubSubChannel:
	"""bind to a single pub/sub channel name."""

	def __init__(self, channel: str) -> None:
		if not channel:
			raise ValueError("channel name must be non-empty")
		self._channel = channel

	@property
	def channel(self) -> str:
		return self._channel

	async def publish(self, payload: dict[str, Any]) -> int:
		"""publish a json payload. returns the number of subscribers reached."""
		conn = redis_client.get()
		body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
		return int(await conn.publish(self._channel, body))

	async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
		"""async iterator over decoded payloads delivered to this channel.

		yields one ``dict`` per published message. ignores subscribe / pong
		envelopes. unsubscribes and closes the redis pubsub connection on
		cancellation or generator close.
		"""
		conn = redis_client.get_pubsub()
		pubsub = conn.pubsub()
		try:
			await pubsub.subscribe(self._channel)
			async for msg in pubsub.listen():
				if msg["type"] != "message":
					continue
				data = msg.get("data")
				if not isinstance(data, (bytes, bytearray)):
					continue
				try:
					payload = json.loads(data)
				except json.JSONDecodeError:
					logger.warning(
						"dropping non-json pubsub frame on %s",
						self._channel,
					)
					continue
				if not isinstance(payload, dict):
					continue
				yield payload
		finally:
			try:
				await pubsub.unsubscribe(self._channel)
			except (RedisError, OSError) as exc:
				logger.debug("pubsub unsubscribe error on %s: %s", self._channel, exc)
			try:
				await pubsub.aclose()
			except (RedisError, OSError) as exc:
				logger.debug("pubsub close error on %s: %s", self._channel, exc)


def make_run_channel(run_id: str, suffix: str) -> PubSubChannel:
	"""build a per-run channel name with a stable prefix.

	keeps key namespacing in one place; callers don't hand-craft keys.
	"""
	return PubSubChannel(f"nokodo_ai:run:{run_id}:{suffix}")


def make_task_channel(task_id: str, suffix: str) -> PubSubChannel:
	"""build a per-task channel name with a stable prefix."""
	return PubSubChannel(f"nokodo_ai:task:{task_id}:{suffix}")
