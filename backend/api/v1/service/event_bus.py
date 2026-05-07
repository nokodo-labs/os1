"""cross-process websocket event fanout over redis pub/sub."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.exceptions import RedisError

from api.redis import PubSubChannel
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_CHANNEL = PubSubChannel("nokodo-ai:events:fanout")
_PROCESS_TOKEN = uuid4().hex

EventBusHandler = Callable[
	[dict[str, object], list[TypeID] | None, TypeID | None, bool],
	Awaitable[None],
]


def _typeid_list(values: object) -> list[TypeID] | None:
	if not isinstance(values, list):
		return None
	result: list[TypeID] = []
	for value in values:
		if not isinstance(value, str):
			continue
		try:
			result.append(TypeID(value))
		except ValueError:
			logger.debug("dropping malformed event recipient id: %s", value)
	return result


def _typeid_value(value: object) -> TypeID | None:
	if not isinstance(value, str) or not value:
		return None
	try:
		return TypeID(value)
	except ValueError:
		logger.debug("dropping malformed event user id: %s", value)
		return None


def _publisher_id() -> str:
	"""return a publisher id that stays unique after process forks."""
	return f"{os.getpid()}:{_PROCESS_TOKEN}"


async def publish_event(
	event_data: dict[str, object],
	recipient_ids: list[TypeID] | None = None,
	user_id: TypeID | str | None = None,
	broadcast: bool = False,
) -> None:
	"""mirror a websocket event to other processes."""
	envelope: dict[str, object] = {
		"publisher_id": _publisher_id(),
		"event": event_data,
		"broadcast": broadcast,
	}
	if recipient_ids is not None:
		envelope["recipient_ids"] = [str(uid) for uid in recipient_ids]
	if user_id is not None:
		envelope["user_id"] = str(user_id)
	try:
		await _CHANNEL.publish(envelope)
	except (RedisError, RuntimeError, OSError) as exc:
		logger.warning("redis event fanout publish failed: %s", exc)


async def start_event_subscriber(handler: EventBusHandler) -> asyncio.Task[None]:
	"""start a background subscriber for remote websocket events."""

	async def _listener() -> None:
		backoff = 0.5
		max_backoff = 5.0
		while True:
			try:
				async for payload in _CHANNEL.subscribe():
					publisher_id = payload.get("publisher_id")
					if publisher_id == _publisher_id():
						continue
					event_data = payload.get("event")
					if not isinstance(event_data, dict):
						continue
					recipient_ids = _typeid_list(payload.get("recipient_ids"))
					user_id = _typeid_value(payload.get("user_id"))
					broadcast = payload.get("broadcast") is True
					await handler(event_data, recipient_ids, user_id, broadcast)
				backoff = 0.5
			except asyncio.CancelledError:
				return
			except Exception:
				logger.exception(
					"event fanout subscriber crashed, reconnecting in %.1fs",
					backoff,
				)
				await asyncio.sleep(backoff)
				backoff = min(backoff * 2, max_backoff)

	return asyncio.create_task(_listener(), name="event-fanout-subscriber")
