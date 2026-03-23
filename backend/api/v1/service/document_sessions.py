"""in-memory collaborative document session store.

tracks active editing sessions per document and manages Yjs CRDT state
for real-time concurrent editing.

## redis migration notes

this module mirrors the user_activity store pattern for easy swap to Redis:
- replace ``_rooms`` dict with Redis hashes (key=doc_id, field=session_id)
- replace ``_lock`` with Redis distributed lock (or remove if using Redis atomics)
- store Yjs binary state in Redis blob (``SET doc:{id}:state <bytes>``)
- ``join()`` becomes ``HSET`` + ``GET`` for state
- ``leave()`` becomes ``HDEL`` + cleanup check
- ``apply_update()`` becomes ``GET`` + merge + ``SET``
- ``leave_all()`` iterates rooms via ``SCAN``

the public API should stay identical after the swap.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pycrdt import Doc

from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


@dataclass
class DocumentParticipant:
	"""a user's presence in a collaborative editing session."""

	user_id: TypeID
	session_id: str
	user_name: str = ""
	avatar_url: str | None = None
	color: str = ""
	joined_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
	awareness: dict[str, object] | None = None


@dataclass
class DocumentRoom:
	"""an active collaborative editing session for a single document."""

	document_id: str
	doc: Doc
	participants: dict[str, DocumentParticipant] = field(default_factory=dict)
	created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class DocumentSessionStore:
	"""manages collaborative editing rooms.

	thread-safe via asyncio.Lock. keyed by document_id (e.g. "note:{uuid}").
	each room holds a pycrdt.Doc for CRDT state and a participant registry.
	"""

	def __init__(self) -> None:
		self._rooms: dict[str, DocumentRoom] = {}
		self._lock = asyncio.Lock()

	async def join(
		self,
		document_id: str,
		user_id: TypeID,
		session_id: str,
		user_name: str = "",
		avatar_url: str | None = None,
		color: str = "",
	) -> bytes:
		"""join (or create) a document room.

		returns full Yjs state as binary update bytes.
		the caller should base64-encode before sending over JSON.
		"""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				room = DocumentRoom(document_id=document_id, doc=Doc())
				self._rooms[document_id] = room
			room.participants[session_id] = DocumentParticipant(
				user_id=user_id,
				session_id=session_id,
				user_name=user_name,
				avatar_url=avatar_url,
				color=color,
			)
			# full state as binary update
			return room.doc.get_update()

	async def leave(
		self,
		document_id: str,
		session_id: str,
	) -> list[DocumentParticipant]:
		"""remove a participant from a document room.

		returns remaining participants. cleans up the room when empty.
		"""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				return []
			room.participants.pop(session_id, None)
			remaining = list(room.participants.values())
			if not remaining:
				del self._rooms[document_id]
			return remaining

	async def apply_update(
		self,
		document_id: str,
		update: bytes,
	) -> bool:
		"""apply a Yjs binary update to the document CRDT.

		returns True on success, False if the room doesn't exist or the
		update is malformed.
		"""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				return False
			try:
				room.doc.apply_update(update)
				return True
			except Exception:
				logger.debug("failed to apply Yjs update to %s", document_id)
				return False

	async def get_participants(
		self,
		document_id: str,
	) -> list[DocumentParticipant]:
		"""get all participants in a document room."""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				return []
			return list(room.participants.values())

	async def update_awareness(
		self,
		document_id: str,
		session_id: str,
		data: dict[str, object],
	) -> None:
		"""update awareness data (cursor, selection, user info) for a participant."""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				return
			participant = room.participants.get(session_id)
			if participant:
				participant.awareness = data

	async def get_all_awareness(
		self,
		document_id: str,
	) -> list[dict[str, object]]:
		"""get awareness data for all participants in a room."""
		async with self._lock:
			room = self._rooms.get(document_id)
			if not room:
				return []
			result: list[dict[str, object]] = []
			for p in room.participants.values():
				entry: dict[str, object] = {
					"user_id": p.user_id,
					"session_id": p.session_id,
				}
				if p.awareness:
					entry.update(p.awareness)
				result.append(entry)
			return result

	async def leave_all(self, session_id: str) -> list[str]:
		"""remove a session from ALL rooms (called on WS disconnect).

		returns the document_ids the session was participating in.
		"""
		async with self._lock:
			left_docs: list[str] = []
			to_cleanup: list[str] = []
			for doc_id, room in self._rooms.items():
				if session_id in room.participants:
					del room.participants[session_id]
					left_docs.append(doc_id)
					if not room.participants:
						to_cleanup.append(doc_id)
			for doc_id in to_cleanup:
				del self._rooms[doc_id]
			return left_docs

	async def get_room_count(self) -> int:
		"""return the number of active document rooms."""
		async with self._lock:
			return len(self._rooms)


# module-level singleton
document_session_store = DocumentSessionStore()
