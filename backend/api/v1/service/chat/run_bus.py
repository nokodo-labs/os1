"""cross-worker run sse bus over redis pub/sub.

problem:

- ``RunStatusStore`` keeps every run's frame log + live subscriber set
  in-process. on a single worker this is perfect: zero hops, zero
  serialization. but with multiple api workers the producer worker is
  unknown at HTTP-subscribe time, so a subscriber landing on the wrong
  worker would 404.

solution:

- producer worker ALWAYS publishes each frame to redis pub/sub
	``nokodo-ai:run:{run_id}:sse`` AND appends to a redis list
	``nokodo-ai:run:{run_id}:log`` (with TTL) for late-subscriber catchup.
- subscribers ALWAYS prefer the local in-process path (zero hops) when
  the run is known locally. when not known locally, they fall back to
  ``subscribe_remote_run`` which fetches catchup via ``LRANGE`` and
  consumes live frames from pub/sub.
- the producer signals end-of-stream by publishing a sentinel envelope
  ``{"end": true}``; remote subscribers translate that to ``None`` so the
  existing live-queue contract is preserved across paths.

key invariants:

- frames published to redis are exactly the bytes that go to local
  subscribers - no transcoding, no double-encoding. this keeps the wire
  format in one place (sse_encode) and lets the subscriber tee through
  the same downstream pipeline regardless of locality.
- the redis log TTL bounds memory; it is sized to outlive the typical
  reconnect window (default 10 minutes - matches the in-process stale
  TTL).
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable
from typing import Final, cast

from redis.exceptions import RedisError

from api.redis import make_run_channel, redis_client
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


_CHANNEL_SUFFIX: Final[str] = "sse"
_LOG_KEY_PREFIX: Final[str] = "nokodo-ai:run:"
_LOG_KEY_SUFFIX: Final[str] = ":log"
_LOG_TTL_SECONDS: Final[int] = 10 * 60  # active-run catchup window
_LOG_MAX_FRAMES: Final[int] = 4096  # bound per-run memory in redis
_LOG_CLEANUP_GRACE_SECONDS: Final[int] = 5  # short window for late catchup
# special log entry that marks "stream ended" for late subscribers who
# read the log via LRANGE after the producer is gone. without this they
# would get the catchup frames and then block forever waiting for a
# pubsub end sentinel that was already broadcast before they subscribed.
_LOG_END_MARKER: Final[bytes] = b"__nokodo_run_end__"
# after a run terminates we shrink the log TTL rather than deleting
# immediately. this keeps a small window for late cross-worker
# subscribers (cross-worker race between mark_run_end and the LRANGE)
# while still letting the key expire so subsequent subscribe attempts
# return UnknownRunError.


def _log_key(run_id: TypeID) -> str:
	return f"{_LOG_KEY_PREFIX}{run_id}{_LOG_KEY_SUFFIX}"


async def mirror_frame(run_id: TypeID, frame: bytes) -> None:
	"""mirror a single sse frame to redis (log append + pub/sub publish).

	transient redis errors are logged and swallowed - the local path has
	already delivered the frame to in-process subscribers, so a redis blip
	only degrades cross-worker fanout for that single frame.
	"""
	try:
		conn = redis_client.get()
		log_key = _log_key(run_id)
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, frame)
		pipe.ltrim(log_key, -_LOG_MAX_FRAMES, -1)
		pipe.expire(log_key, _LOG_TTL_SECONDS)
		await pipe.execute()
		envelope = {"frame_b64": base64.b64encode(frame).decode("ascii")}
		await make_run_channel(str(run_id), _CHANNEL_SUFFIX).publish(envelope)
	except (RedisError, OSError) as exc:
		logger.warning("redis sse mirror failed for run %s: %s", run_id, exc)


async def mark_run_end(run_id: TypeID) -> None:
	"""publish the end-of-stream sentinel for ``run_id``.

	remote subscribers translate this to the same terminal ``None`` that
	in-process subscribers receive on the local queue. additionally
	appends an end marker to the catchup log so late subscribers reading
	via LRANGE detect completion without blocking on a pubsub message
	that was already broadcast before they subscribed.
	"""
	try:
		conn = redis_client.get()
		log_key = _log_key(run_id)
		pipe = conn.pipeline(transaction=False)
		pipe.rpush(log_key, _LOG_END_MARKER)
		pipe.ltrim(log_key, -_LOG_MAX_FRAMES, -1)
		pipe.expire(log_key, _LOG_TTL_SECONDS)
		await pipe.execute()
		await make_run_channel(str(run_id), _CHANNEL_SUFFIX).publish({"end": True})
	except (RedisError, OSError) as exc:
		logger.warning("redis sse end mark failed for run %s: %s", run_id, exc)


async def subscribe_remote_run(run_id: TypeID) -> AsyncIterator[bytes]:
	"""subscribe to a run owned by another worker.

	yields the catchup log first, then live frames forwarded over redis
	pub/sub, until either an end sentinel is received or the caller stops
	iterating.

	subscribe-before-catchup ordering: the pub/sub SUBSCRIBE round-trips
	BEFORE the ``LRANGE`` catchup runs so frames published during the
	catchup window are still delivered (rather than lost). a frame
	published in the small overlap may be delivered twice (once via
	catchup, once via pub/sub) - benign for SSE consumers; a sequence-id
	dedup scheme is left for a follow-up if duplicate frames ever cause
	client confusion.
	"""
	conn = redis_client.get()
	channel_name = make_run_channel(str(run_id), _CHANNEL_SUFFIX).channel
	log_key = _log_key(run_id)
	pubsub = redis_client.get_pubsub().pubsub()
	try:
		# 1) establish the subscription FIRST so the broker is forwarding
		# any concurrently-published frames into our connection buffer.
		await pubsub.subscribe(channel_name)
		# 2) read the catchup log; frames published between (1) and (2)
		# will appear both here and in the live loop (acceptable dup).
		# if the log already contains the end marker, the producer has
		# terminated - yield catchup frames up to the marker and exit
		# without entering the live loop.
		catchup_raw: list[bytes] = await cast(
			"Awaitable[list[bytes]]", conn.lrange(log_key, 0, -1)
		)
		ended_in_catchup = False
		for frame in catchup_raw:
			if not isinstance(frame, (bytes, bytearray)):
				continue
			frame_b = bytes(frame)
			if frame_b == _LOG_END_MARKER:
				ended_in_catchup = True
				break
			yield frame_b
		if ended_in_catchup:
			return
		# 3) drain live frames until end sentinel.
		async for msg in pubsub.listen():
			if msg["type"] != "message":
				continue
			data = msg.get("data")
			if not isinstance(data, (bytes, bytearray)):
				continue
			try:
				envelope = json.loads(data)
			except json.JSONDecodeError:
				logger.debug("dropping non-json sse envelope on run %s", run_id)
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
				logger.debug("dropping malformed remote sse frame for run %s", run_id)
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


async def remote_run_known(run_id: TypeID) -> bool:
	"""best-effort check: does redis have any log entries for this run?

	used by the SSE entry point to distinguish "unknown run" (404) from
	"run owned elsewhere" (subscribe via redis). false-negatives are
	tolerable - they degrade to UnknownRunError which the client retries.
	"""
	try:
		conn = redis_client.get()
		exists = await conn.exists(_log_key(run_id))
		return bool(exists)
	except (RedisError, OSError):
		return False


async def cleanup_run_log(run_id: TypeID) -> None:
	"""shrink the redis catchup log TTL after a run terminates.

	rather than deleting the key outright (which races with late
	cross-worker subscribers between ``mark_run_end`` and their
	``LRANGE``), we set a short expiry. cross-worker subscribers landing
	within the grace window still see the catchup log + end sentinel;
	subsequent subscribers find the key gone and get ``UnknownRunError``.
	"""
	try:
		conn = redis_client.get()
		await conn.expire(_log_key(run_id), _LOG_CLEANUP_GRACE_SECONDS)
	except (RedisError, OSError) as exc:
		logger.warning("redis sse cleanup failed for run %s: %s", run_id, exc)
