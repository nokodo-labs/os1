"""temporary chat message references resolved by the API runner.

these references let SDK hooks and TaskIQ workers talk about a future chat
message without pretending the SDK owns the final database id.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from typing import Final, cast

from redis.exceptions import RedisError

from api.redis import redis_client
from nokodo_ai.utils.typeid import TypeID, new_typeid


logger = logging.getLogger(__name__)

_PREFIX: Final[str] = "nokodo-ai:chat:message-ref:"
_REFERENCE_TTL_SECONDS: Final[int] = 60 * 60
_REFERENCE_WAIT_SECONDS: Final[int] = 60


def new_message_reference() -> str:
	"""create a run-local reference for a future persisted message."""
	return str(new_typeid("msg_ref"))


def _value_key(reference_id: str) -> str:
	return f"{_PREFIX}{reference_id}:value"


def _ready_key(reference_id: str) -> str:
	return f"{_PREFIX}{reference_id}:ready"


def _encode_payload(payload: dict[str, str]) -> bytes:
	return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _decode_payload(raw: object) -> dict[str, str] | None:
	if not isinstance(raw, (bytes, bytearray)):
		return None
	try:
		decoded = json.loads(raw.decode("utf-8"))
	except UnicodeDecodeError, json.JSONDecodeError:
		return None
	if not isinstance(decoded, dict):
		return None
	payload: dict[str, str] = {}
	for key, value in decoded.items():
		if isinstance(key, str) and isinstance(value, str):
			payload[key] = value
	return payload


async def _publish_reference(reference_id: str, payload: dict[str, str]) -> bool:
	"""store and wake a one-shot message reference if it is still pending."""
	try:
		conn = redis_client.get()
		encoded = _encode_payload(payload)
		stored = await conn.set(
			_value_key(reference_id),
			encoded,
			ex=_REFERENCE_TTL_SECONDS,
			nx=True,
		)
		if not stored:
			return False
		pipe = conn.pipeline(transaction=False)
		pipe.lpush(_ready_key(reference_id), encoded)
		pipe.expire(_ready_key(reference_id), _REFERENCE_TTL_SECONDS)
		await pipe.execute()
		return True
	except RedisError, OSError, RuntimeError:
		logger.exception(
			"failed to publish message reference",
			extra={"message_ref": reference_id},
		)
		return False


async def resolve_message_reference(
	reference_id: str,
	message_id: str | TypeID,
) -> bool:
	"""resolve a temporary reference to the persisted message id."""
	return await _publish_reference(
		reference_id,
		{"status": "resolved", "message_id": str(message_id)},
	)


async def reject_message_reference(reference_id: str, reason: str) -> bool:
	"""reject a temporary reference so waiters can stop waiting."""
	return await _publish_reference(
		reference_id,
		{"status": "rejected", "reason": reason},
	)


def _resolved_message_id(payload: dict[str, str] | None) -> str | None:
	if not payload:
		return None
	if payload.get("status") != "resolved":
		return None
	message_id = payload.get("message_id")
	return message_id or None


async def wait_message_reference(
	reference_id: str,
	timeout_seconds: int = _REFERENCE_WAIT_SECONDS,
) -> str | None:
	"""wait for a temporary reference to resolve to a persisted message id."""
	try:
		conn = redis_client.get()
		raw = await conn.get(_value_key(reference_id))
		message_id = _resolved_message_id(_decode_payload(raw))
		if message_id is not None:
			return message_id

		popped = await cast(
			"Awaitable[object | None]",
			conn.blpop([_ready_key(reference_id)], timeout=timeout_seconds),
		)
		if popped is None:
			logger.warning(
				"timed out waiting for message reference",
				extra={"message_ref": reference_id},
			)
			return None
		if not isinstance(popped, (list, tuple)) or len(popped) != 2:
			return None
		_, ready_raw = popped
		message_id = _resolved_message_id(_decode_payload(ready_raw))
		if message_id is not None:
			return message_id

		raw = await conn.get(_value_key(reference_id))
		return _resolved_message_id(_decode_payload(raw))
	except RedisError, OSError, RuntimeError:
		logger.exception(
			"failed to wait for message reference",
			extra={"message_ref": reference_id},
		)
		return None
