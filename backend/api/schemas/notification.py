"""notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from api.schemas.common import ORMModel, TimestampedModel
from api.schemas.event import Event
from nokodo_ai.utils.typeid import TypeID


class NotificationBase(ORMModel):
	"""mutable notification fields."""

	user_id: TypeID
	event_id: TypeID
	dismissed: bool = False


class Notification(NotificationBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	read_at: datetime | None = None
	event: Event | None = None


class NotificationCreate(BaseModel):
	"""request schema for creating notification(s)."""

	title: str
	body: str
	user_ids: list[TypeID]


class NotificationListFilters(BaseModel):
	"""filters for listing notifications."""

	only_unread: bool = False
