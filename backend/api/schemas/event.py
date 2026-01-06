"""Event schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.event import EventScope
from api.schemas.common import MetadataModel
from nokodo_ai.utils.typeid import TypeID


class EventBase(MetadataModel):
	"""Shared event attributes."""

	scope: EventScope = EventScope.SYSTEM
	scope_id: TypeID | None = None
	type: str
	data: dict[str, Any] = Field(default_factory=dict)
	expires_at: datetime | None = None
	version: int = 1
	user_id: TypeID | None = None
	thread_id: TypeID | None = None
	message_id: TypeID | None = None
	task_id: TypeID | None = None


class EventCreate(EventBase):
	"""Payload to emit a new event."""

	pass


class Event(EventBase):
	"""Event response."""

	id: TypeID
	created_at: datetime
	updated_at: datetime


class EventsByMessageIDsRequest(MetadataModel):
	"""Request payload to fetch events for a set of messages."""

	message_ids: list[TypeID] = Field(default_factory=list, max_length=500)
