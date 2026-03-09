"""ThreadParticipant schemas."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import ORMModel
from nokodo_ai.utils.typeid import TypeID


class ThreadParticipant(ORMModel):
	"""response schema for a thread participant."""

	id: TypeID
	thread_id: TypeID
	user_id: TypeID | None = None
	agent_id: TypeID | None = None
	membership_role: str | None = None
	joined_at: datetime
	left_at: datetime | None = None
	last_read_message_id: TypeID | None = None


class ThreadUnreadCount(ORMModel):
	"""unread count for a single thread."""

	thread_id: TypeID
	unread_count: int
