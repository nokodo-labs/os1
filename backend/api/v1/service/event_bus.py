"""cross-process websocket fanout relay over redis pub/sub."""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from uuid import uuid4

from redis.exceptions import RedisError

from api.redis import PubSubChannel
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_FANOUT_CHANNEL = PubSubChannel("nokodo-ai:events:fanout")
_SOCKET_KILL_CHANNEL = PubSubChannel("nokodo-ai:events:socket-kill")
_PROCESS_TOKEN = uuid4().hex

RemoteFanoutHandler = Callable[
	[dict[str, object], list[TypeID] | None, TypeID | None, bool, TypeID | None],
	Awaitable[None],
]

SocketKillHandler = Callable[[TypeID], Awaitable[None]]
ServerEventHandler = Callable[[dict[str, object]], Awaitable[None]]
ReconnectHandler = Callable[[], Awaitable[None]]

_server_event_handlers: dict[str, list[ServerEventHandler]] = {}


def register_server_event_handler(
	event_type: str,
	handler: ServerEventHandler,
) -> None:
	"""register a process-local handler for one cross-process event type."""
	handlers = _server_event_handlers.setdefault(event_type, [])
	if handler not in handlers:
		handlers.append(handler)


async def dispatch_server_event(stream_payload: dict[str, object]) -> None:
	"""run live local handlers; durable persisted-event replay may be added later."""
	event_type = stream_payload.get("type")
	if not isinstance(event_type, str):
		return
	for handler in _server_event_handlers.get(event_type, []):
		try:
			await handler(stream_payload)
		except Exception:
			logger.exception(
				"server event handler failed",
				extra={"event_type": event_type},
			)


def _typeid_list(values: object) -> list[TypeID] | None:
	"""parse a list of TypeID strings from a Redis event envelope."""
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
	"""parse one optional TypeID from a Redis event envelope."""
	if not isinstance(value, str) or not value:
		return None
	try:
		return TypeID(value)
	except ValueError:
		logger.debug("dropping malformed event user id: %s", value)
		return None


def _process_fanout_id() -> str:
	"""return a publisher id that stays unique after process forks."""
	return f"{os.getpid()}:{_PROCESS_TOKEN}"


async def publish_remote_fanout(
	stream_payload: dict[str, object],
	recipient_ids: list[TypeID] | None = None,
	user_id: TypeID | str | None = None,
	broadcast: bool = False,
	exclude_user_id: TypeID | str | None = None,
) -> None:
	"""relay a websocket payload to other backend processes only."""
	envelope: dict[str, object] = {
		"publisher_id": _process_fanout_id(),
		"event": stream_payload,
		"broadcast": broadcast,
	}
	if recipient_ids is not None:
		envelope["recipient_ids"] = [str(uid) for uid in recipient_ids]
	if user_id is not None:
		envelope["user_id"] = str(user_id)
	if exclude_user_id is not None:
		envelope["exclude_user_id"] = str(exclude_user_id)
	try:
		await _FANOUT_CHANNEL.publish(envelope)
	except (RedisError, RuntimeError, OSError) as exc:
		logger.warning("redis event fanout publish failed: %s", exc)


async def start_remote_fanout_listener(
	handler: RemoteFanoutHandler,
	on_connected: ReconnectHandler | None = None,
) -> asyncio.Task[None]:
	"""start a background listener for websocket payloads from other processes."""

	async def _listener() -> None:
		backoff = 0.5
		max_backoff = 5.0
		while True:
			try:
				async with _FANOUT_CHANNEL.attached() as messages:
					if on_connected is not None:
						await on_connected()
					async for payload in messages:
						publisher_id = payload.get("publisher_id")
						if publisher_id == _process_fanout_id():
							continue
						event_data = payload.get("event")
						if not isinstance(event_data, dict):
							continue
						recipient_ids = _typeid_list(payload.get("recipient_ids"))
						user_id = _typeid_value(payload.get("user_id"))
						broadcast = payload.get("broadcast") is True
						exclude_user_id = _typeid_value(payload.get("exclude_user_id"))
						await handler(
							event_data,
							recipient_ids,
							user_id,
							broadcast,
							exclude_user_id,
						)
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


async def publish_socket_kill(user_id: TypeID) -> None:
	"""ask every backend process to close the user's live websockets."""
	try:
		await _SOCKET_KILL_CHANNEL.publish({"user_id": str(user_id)})
	except (RedisError, RuntimeError, OSError) as exc:
		logger.warning("redis socket kill publish failed: %s", exc)


async def start_socket_kill_listener(
	handler: SocketKillHandler,
) -> asyncio.Task[None]:
	"""start a background listener that closes sockets on kill signals.

	unlike the fanout relay, kill signals are NOT publisher-filtered: the
	publishing process must also close its own local sockets via this path.
	"""

	async def _listener() -> None:
		backoff = 0.5
		max_backoff = 5.0
		while True:
			try:
				async for payload in _SOCKET_KILL_CHANNEL.subscribe():
					user_id = _typeid_value(payload.get("user_id"))
					if user_id is None:
						continue
					await handler(user_id)
				backoff = 0.5
			except asyncio.CancelledError:
				return
			except Exception:
				logger.exception(
					"socket kill subscriber crashed, reconnecting in %.1fs",
					backoff,
				)
				await asyncio.sleep(backoff)
				backoff = min(backoff * 2, max_backoff)

	return asyncio.create_task(_listener(), name="socket-kill-subscriber")
