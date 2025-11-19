"""Event schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.event import EventScope
from api.schemas.common import MetadataModel


class EventBase(MetadataModel):
	"""Shared event attributes."""

	scope: EventScope = EventScope.SYSTEM
	scope_id: str | None = None
	type: str
	data: dict[str, Any] = Field(default_factory=dict)
	expires_at: datetime | None = None
	version: int = 1
	user_id: int | None = None
	thread_id: str | None = None
	message_id: str | None = None
	task_id: str | None = None


class EventCreate(EventBase):
	"""Payload to emit a new event."""

	pass


class Event(EventBase):
	"""Event response."""

	id: str
	created_at: datetime
	updated_at: datetime
