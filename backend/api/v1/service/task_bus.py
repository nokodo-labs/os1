"""cross-worker task SSE bus over Redis pub/sub."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator
from typing import Final

from redis.exceptions import RedisError

from api.redis import make_task_channel, redis_client
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_CHANNEL_SUFFIX: Final[str] = "sse"
_LOG_KEY_PREFIX: Final[str] = "nokodo-ai:task:"
_LOG_KEY_SUFFIX: Final[str] = ":log"
_LOG_TTL_SECONDS: Final[int] = 60 * 60 * 24
_LOG_MAX_FRAMES: Final[int] = 2048
_LOG_END_MARKER: Final[bytes] = b"__nokodo_task_end__"


def _log_key(task_id: TypeID) -> str:
	return f"{_LOG_KEY_PREFIX}{task_id}{_LOG_KEY_SUFFIX}"


async def mirror_frame(task_id: TypeID, frame: bytes) -> None:
	"""mirror a task SSE frame to Redis for resume/cross-worker clients."""
	try:
		conn = redis_client.get()
		log_key = _log_key(task_id)
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, frame)
		pipe.ltrim(log_key, -_LOG_MAX_FRAMES, -1)
		pipe.expire(log_key, _LOG_TTL_SECONDS)
		await pipe.execute()
		envelope = {"frame_b64": base64.b64encode(frame).decode("ascii")}
		await make_task_channel(str(task_id), _CHANNEL_SUFFIX).publish(envelope)
	except (RedisError, RuntimeError, OSError) as exc:
		logger.warning("redis task sse mirror failed for task %s: %s", task_id, exc)


async def mark_task_end(task_id: TypeID) -> None:
	"""publish and log the task stream terminal marker."""
	try:
		conn = redis_client.get()
		log_key = _log_key(task_id)
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, _LOG_END_MARKER)
		pipe.ltrim(log_key, -_LOG_MAX_FRAMES, -1)
		pipe.expire(log_key, _LOG_TTL_SECONDS)
		await pipe.execute()
		await make_task_channel(str(task_id), _CHANNEL_SUFFIX).publish({"end": True})
	except (RedisError, RuntimeError, OSError) as exc:
		logger.warning("redis task sse end mark failed for task %s: %s", task_id, exc)


async def subscribe_task_stream(task_id: TypeID) -> AsyncIterator[bytes]:
	"""yield logged task frames first, then live frames until task end."""
	conn = redis_client.get()
	channel_name = make_task_channel(str(task_id), _CHANNEL_SUFFIX).channel
	log_key = _log_key(task_id)
	pubsub = redis_client.get_pubsub().pubsub()
	try:
		await pubsub.subscribe(channel_name)
		catchup_result = conn.lrange(log_key, 0, -1)
		if isinstance(catchup_result, list):
			catchup_raw = catchup_result
		else:
			catchup_raw = await catchup_result
		ended_in_catchup = False
		if isinstance(catchup_raw, list):
			for frame in catchup_raw:
				if not isinstance(frame, (bytes, bytearray)):
					continue
				frame_bytes = bytes(frame)
				if frame_bytes == _LOG_END_MARKER:
					ended_in_catchup = True
					break
				yield frame_bytes
		if ended_in_catchup:
			return

		async for msg in pubsub.listen():
			if msg["type"] != "message":
				continue
			data = msg.get("data")
			if not isinstance(data, (bytes, bytearray)):
				continue
			try:
				envelope = json.loads(data)
			except json.JSONDecodeError:
				logger.debug("dropping non-json task sse envelope for task %s", task_id)
				continue
			if not isinstance(envelope, dict):
				continue
			if envelope.get("end") is True:
				return
			raw_b64 = envelope.get("frame_b64")
			if not isinstance(raw_b64, str):
				continue
			try:
				yield base64.b64decode(raw_b64.encode("ascii"))
			except (ValueError, TypeError):
				logger.debug("dropping malformed task sse frame for task %s", task_id)
				continue
	finally:
		try:
			await pubsub.unsubscribe(channel_name)
		except (RedisError, OSError) as exc:
			logger.debug("pubsub unsubscribe error on %s: %s", channel_name, exc)
		try:
			await pubsub.aclose()
		except (RedisError, OSError) as exc:
			logger.debug("pubsub close error on %s: %s", channel_name, exc)


async def task_log_known(task_id: TypeID) -> bool:
	"""return whether Redis has catchup frames for this task."""
	try:
		conn = redis_client.get()
		exists = await conn.exists(_log_key(task_id))
		return bool(exists)
	except (RedisError, RuntimeError, OSError):
		return False
