"""Notification schemas."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import ORMModel
from api.schemas.event import Event
from api.typeid import TypeID


class NotificationBase(ORMModel):
	"""Mutable notification fields."""

	user_id: TypeID
	event_id: TypeID
	dismissed: bool = False


class Notification(NotificationBase):
	"""Response schema."""

	id: TypeID
	read_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
	event: Event | None = None
