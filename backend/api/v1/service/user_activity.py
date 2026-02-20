"""in-memory user activity store.

tracks which users are currently connected to the event WebSocket,
serving as a lightweight presence system.

## redis migration notes

this module mirrors the design of ``chat.run_status`` for easy swap to Redis:
- replace ``_active`` dict with Redis hash (key per user_id, value = json metadata)
- replace ``_lock`` with Redis distributed lock (or remove if using Redis atomics)
- ``mark_active()`` becomes ``HSET active_users <user_id> <json>``
- ``mark_inactive()`` becomes ``HDEL active_users <user_id>``
- ``get_active_user_ids()`` becomes ``HKEYS active_users``
- connection count tracking becomes ``HINCRBY`` / ``HDECRBY``
- ``last_active_at`` is persisted to DB on disconnect (unchanged)

the public API (mark_active, mark_inactive, is_active, get_active_user_ids)
should stay identical after the swap.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime


logger = logging.getLogger(__name__)


@dataclass
class UserPresence:
	"""presence metadata for a connected user."""

	user_id: str
	connection_count: int = 1
	connected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	last_seen_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

	def touch(self) -> None:
		self.last_seen_at = datetime.now(tz=UTC)


class UserActivityStore:
	"""singleton store for user presence / activity tracking.

	thread-safe via asyncio.Lock. keyed by user_id.
	tracks how many WS connections each user has (multi-tab support).
	"""

	def __init__(self) -> None:
		self._active: dict[str, UserPresence] = {}
		self._lock = asyncio.Lock()

	async def mark_active(self, user_id: str) -> None:
		"""register a new WS connection for a user."""
		async with self._lock:
			existing = self._active.get(user_id)
			if existing:
				existing.connection_count += 1
				existing.touch()
			else:
				self._active[user_id] = UserPresence(user_id=user_id)

	async def mark_inactive(self, user_id: str) -> datetime:
		"""unregister a WS connection. returns the last_seen_at timestamp.

		only removes presence entry when connection_count drops to zero.
		"""
		async with self._lock:
			existing = self._active.get(user_id)
			if not existing:
				return datetime.now(tz=UTC)

			existing.connection_count -= 1
			existing.touch()
			last_seen = existing.last_seen_at

			if existing.connection_count <= 0:
				del self._active[user_id]

			return last_seen

	async def touch(self, user_id: str) -> None:
		"""update last_seen_at for a user (e.g. on ping)."""
		async with self._lock:
			existing = self._active.get(user_id)
			if existing:
				existing.touch()

	async def is_active(self, user_id: str) -> bool:
		"""check if a user currently has any WS connections."""
		async with self._lock:
			return user_id in self._active

	async def get_active_user_ids(self) -> list[str]:
		"""return all currently active user IDs."""
		async with self._lock:
			return list(self._active.keys())

	async def get_active_count(self) -> int:
		"""return the number of currently active users."""
		async with self._lock:
			return len(self._active)


# module-level singleton
user_activity_store = UserActivityStore()
