"""cross-worker SSE frame bus over redis pub/sub + a catchup log.

one mechanism, two users (agent runs and tasks). a producer worker mirrors
every frame it sends locally to redis: appended to a capped, TTL'd list so a
late subscriber can catch up, and published on a channel so live subscribers
get it immediately. subscribers that do not own the producer read both, in
that order.

the SUBSCRIBE round-trips BEFORE the catchup ``LRANGE`` so frames published
during the catchup window are delivered rather than lost. a frame landing in
that small overlap may arrive twice - benign for SSE consumers, and the
alternative (catchup first) drops frames instead.
"""

import base64
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Final, cast

from redis.exceptions import RedisError

from api.redis.client import redis_client
from api.redis.pubsub import PubSubChannel


logger = logging.getLogger(__name__)

_CHANNEL_SUFFIX: Final[str] = "sse"
"""every bus keys its channel off the owning resource id plus this suffix."""


class SseFrameBus:
	"""mirror and replay one resource kind's SSE frames across workers.

	``log_ttl_seconds`` bounds how long a finished stream stays catchup-able,
	and ``max_frames`` bounds per-resource memory in redis; both are per-domain
	tuning (a run is minutes, a task can be a day) and the only thing instances
	are expected to differ on.
	"""

	def __init__(
		self,
		key_prefix: str,
		end_marker: bytes,
		channel_factory: Callable[[str, str], PubSubChannel],
		log_ttl_seconds: int,
		max_frames: int,
		cleanup_grace_seconds: int,
		truncated_marker: bytes | None = None,
	) -> None:
		self._key_prefix = key_prefix
		self._end_marker = end_marker
		self._channel_factory = channel_factory
		self._log_ttl_seconds = log_ttl_seconds
		self._max_frames = max_frames
		self._cleanup_grace_seconds = cleanup_grace_seconds
		self._truncated_marker = truncated_marker

	def _log_key(self, resource_id: str) -> str:
		return f"{self._key_prefix}{resource_id}:log"

	def _channel(self, resource_id: str) -> PubSubChannel:
		return self._channel_factory(resource_id, _CHANNEL_SUFFIX)

	async def _append(self, resource_id: str, entry: bytes) -> None:
		"""append to the capped catchup log and refresh its TTL."""
		conn = redis_client.get()
		log_key = self._log_key(resource_id)
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, entry)
		pipe.ltrim(log_key, -self._max_frames, -1)
		pipe.expire(log_key, self._log_ttl_seconds)
		await pipe.execute()

	async def _append_and_publish(
		self,
		resource_id: str,
		entry: bytes,
		payload: dict[str, object],
	) -> None:
		"""append and publish one entry in a single ordered Redis pipeline."""
		conn = redis_client.get()
		log_key = self._log_key(resource_id)
		channel = self._channel(resource_id)
		body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, entry)
		pipe.ltrim(log_key, -self._max_frames, -1)
		pipe.expire(log_key, self._log_ttl_seconds)
		pipe.publish(channel.channel, body)
		await pipe.execute()

	async def mirror_frame(self, resource_id: str, frame: bytes) -> None:
		"""log a frame for catchup and publish it to live remote subscribers.

		redis errors are swallowed: the local path already delivered this frame
		to in-process subscribers, so a blip only degrades cross-worker fanout
		for that one frame.
		"""
		try:
			await self._append_and_publish(
				resource_id,
				frame,
				{"frame_b64": base64.b64encode(frame).decode("ascii")},
			)
		except (RedisError, RuntimeError, OSError) as exc:
			logger.warning(
				"redis sse mirror failed for %s%s: %s",
				self._key_prefix,
				resource_id,
				exc,
			)

	async def mirror_frames(self, resource_id: str, frames: list[bytes]) -> None:
		"""log and publish an ordered batch in one Redis round trip."""
		if not frames:
			return
		try:
			conn = redis_client.get()
			log_key = self._log_key(resource_id)
			channel = self._channel(resource_id)
			pipe = conn.pipeline(transaction=False)
			pipe.rpush(log_key, *frames)
			pipe.ltrim(log_key, -self._max_frames, -1)
			pipe.expire(log_key, self._log_ttl_seconds)
			for frame in frames:
				body = json.dumps(
					{"frame_b64": base64.b64encode(frame).decode("ascii")},
					separators=(",", ":"),
				).encode("utf-8")
				pipe.publish(channel.channel, body)
			await pipe.execute()
		except (RedisError, RuntimeError, OSError) as exc:
			logger.warning(
				"redis sse batch mirror failed for %s%s: %s",
				self._key_prefix,
				resource_id,
				exc,
			)

	async def mark_end(self, resource_id: str) -> None:
		"""signal end-of-stream to live AND future subscribers.

		the marker goes in the log as well as on the channel: a subscriber that
		arrives after the producer is gone reads the log and would otherwise
		block forever waiting for a sentinel that was already broadcast.
		"""
		try:
			await self._append_and_publish(
				resource_id,
				self._end_marker,
				{"end": True},
			)
		except (RedisError, RuntimeError, OSError) as exc:
			logger.warning(
				"redis sse end mark failed for %s%s: %s",
				self._key_prefix,
				resource_id,
				exc,
			)

	async def subscribe(self, resource_id: str) -> AsyncIterator[bytes]:
		"""yield the catchup log, then live frames, until the stream ends."""
		channel = self._channel(resource_id)
		# attached, not subscribe: the SUBSCRIBE must land BEFORE the catchup
		# read, or frames published while it is in flight are lost. a frame
		# landing in that overlap arrives twice instead, which SSE consumers
		# tolerate and a gap is not.
		async with channel.attached() as live:
			conn = redis_client.get()
			catchup: list[bytes] = await cast(
				"Awaitable[list[bytes]]",
				conn.lrange(self._log_key(resource_id), 0, -1),
			)
			if (
				self._truncated_marker is not None
				and len(catchup) >= self._max_frames
				and catchup[0] != self._end_marker
			):
				yield self._truncated_marker
			for entry in catchup:
				if not isinstance(entry, (bytes, bytearray)):
					continue
				frame = bytes(entry)
				if frame == self._end_marker:
					# producer already finished; never enter the live loop.
					return
				yield frame
			async for envelope in live:
				if envelope.get("end") is True:
					return
				raw_b64 = envelope.get("frame_b64")
				if not isinstance(raw_b64, str):
					continue
				try:
					yield base64.b64decode(raw_b64.encode("ascii"))
				except ValueError, TypeError:
					logger.debug("dropping malformed sse frame on %s", channel.channel)
					continue

	async def log_known(self, resource_id: str) -> bool:
		"""whether redis still holds a catchup log for this resource.

		false-negatives are tolerable: callers degrade to "unknown", which the
		client retries.
		"""
		try:
			conn = redis_client.get()
			return bool(await conn.exists(self._log_key(resource_id)))
		except RedisError, RuntimeError, OSError:
			return False

	async def cleanup_log(self, resource_id: str) -> None:
		"""shrink the log TTL once a stream has ended.

		a short expiry rather than a delete: deleting races with a late
		subscriber between ``mark_end`` and its catchup read, and that
		subscriber would lose the terminal frames entirely.

		failing only means the log lives out its full TTL, which is the state
		it was already in - not worth telling anyone about.
		"""
		with contextlib.suppress(RedisError, RuntimeError, OSError):
			conn = redis_client.get()
			await conn.expire(self._log_key(resource_id), self._cleanup_grace_seconds)
