"""in-memory user presence tracking."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass
class _UserPresence:
	"""presence metadata for a connected user."""

	user_id: str
	connection_count: int = 1
	connected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	last_seen_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

	def touch(self) -> None:
		self.last_seen_at = datetime.now(tz=UTC)


_active: dict[str, _UserPresence] = {}
_lock = asyncio.Lock()


async def mark_user_active(user_id: TypeID | str) -> None:
	"""register a WebSocket connection for a user."""
	key = str(user_id)
	async with _lock:
		existing = _active.get(key)
		if existing:
			existing.connection_count += 1
			existing.touch()
		else:
			_active[key] = _UserPresence(user_id=key)


async def mark_user_inactive(user_id: TypeID | str) -> datetime:
	"""unregister a WebSocket connection and return its last seen time."""
	key = str(user_id)
	async with _lock:
		existing = _active.get(key)
		if not existing:
			return datetime.now(tz=UTC)
		existing.connection_count -= 1
		existing.touch()
		last_seen = existing.last_seen_at
		if existing.connection_count <= 0:
			del _active[key]
		return last_seen


async def touch_user_activity(user_id: TypeID | str) -> None:
	"""update a connected user's last seen time."""
	async with _lock:
		existing = _active.get(str(user_id))
		if existing:
			existing.touch()


async def is_user_active(user_id: TypeID | str) -> bool:
	"""return whether a user has any WebSocket connections."""
	async with _lock:
		return str(user_id) in _active


async def list_active_user_ids() -> list[str]:
	"""return IDs of users with WebSocket connections."""
	async with _lock:
		return list(_active)


async def count_active_users() -> int:
	"""return the number of users with WebSocket connections."""
	async with _lock:
		return len(_active)
