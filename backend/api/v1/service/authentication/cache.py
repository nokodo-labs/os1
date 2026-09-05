"""redis caches for principal snapshots and session validity."""

import asyncio
import logging

from api.redis import cache
from api.settings import settings
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_PRINCIPAL_KEY = "principal:{user_id}"
_SESSION_KEY = "session_alive:{session_id}"
_ROLE_TAG = "principal-role:{role_id}"

SNAPSHOT_VERSION = 2


def _principal_key(user_id: TypeID | str) -> str:
	"""cache key for a user's principal snapshot."""
	return _PRINCIPAL_KEY.format(user_id=user_id)


def _session_key(session_id: TypeID | str) -> str:
	"""cache key for a session's validity flag."""
	return _SESSION_KEY.format(session_id=session_id)


async def get_principal_snapshot(user_id: TypeID | str) -> dict[str, object] | None:
	"""fetch the cached principal snapshot for a user, if fresh."""
	cached = await cache.get(_principal_key(user_id))
	if not isinstance(cached, dict):
		return None
	snapshot: dict[str, object] = {str(k): v for k, v in cached.items()}
	if snapshot.get("v") != SNAPSHOT_VERSION:
		return None
	return snapshot


async def store_principal_snapshot(
	user_id: TypeID | str,
	snapshot: dict[str, object],
	role_ids: list[str],
) -> None:
	"""cache a principal snapshot, tagged per role for group invalidation."""
	snapshot["v"] = SNAPSHOT_VERSION
	await cache.set(
		_principal_key(user_id),
		snapshot,
		ttl=settings.cache.principal_ttl_seconds,
		tags=[_ROLE_TAG.format(role_id=role_id) for role_id in role_ids],
	)


async def _invalidate_principal(user_id: TypeID | str) -> None:
	"""drop the cached principal for one user."""
	if not await cache.delete(_principal_key(user_id)):
		logger.warning(
			"principal invalidation write failed for user %s; "
			"stale permissions possible until cache TTL expiry",
			user_id,
		)


async def invalidate_principals(user_ids: list[TypeID] | list[str]) -> None:
	"""drop cached principals for several users."""
	await asyncio.gather(*(_invalidate_principal(uid) for uid in user_ids))


async def invalidate_principals_for_role(role_id: TypeID | str) -> None:
	"""drop every cached principal that carries the given role."""
	if not await cache.invalidate_tag(_ROLE_TAG.format(role_id=role_id)):
		logger.warning(
			"principal invalidation write failed for role %s; "
			"stale permissions possible until cache TTL expiry",
			role_id,
		)


async def get_session_validity(session_id: TypeID | str) -> bool | None:
	"""cached session validity, or None when unknown."""
	cached = await cache.get(_session_key(session_id))
	return cached if isinstance(cached, bool) else None


async def fill_session_validity(session_id: TypeID | str, alive: bool) -> None:
	"""cache a DB-derived validity flag without clobbering a write-through."""
	await cache.set(
		_session_key(session_id),
		alive,
		ttl=settings.cache.session_validity_ttl_seconds,
		nx=True,
	)


async def mark_session_revoked(session_id: TypeID | str) -> None:
	"""write through a single session revocation."""
	written = await cache.set(
		_session_key(session_id),
		False,
		ttl=settings.cache.session_validity_ttl_seconds,
	)
	if not written:
		logger.warning(
			"session revocation write-through failed for session %s; "
			"revocation may lag until cache TTL expiry",
			session_id,
		)


async def mark_sessions_revoked(session_ids: list[TypeID]) -> None:
	"""write through a bulk session revocation."""
	await asyncio.gather(*(mark_session_revoked(sid) for sid in session_ids))
