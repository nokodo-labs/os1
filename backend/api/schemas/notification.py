"""Notification schemas."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import ORMModel
from api.schemas.event import Event


class NotificationBase(ORMModel):
	"""Mutable notification fields."""

	user_id: int
	event_id: str
	dismissed: bool = False


class Notification(NotificationBase):
	"""Response schema."""

	id: str
	read_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
	event: Event | None = None
