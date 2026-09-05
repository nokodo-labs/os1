"""event schemas."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from api.models.event import Event as EventModel
from api.models.event import EventScope
from api.schemas.common import ForbidExtraModel, MetadataModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class EventListFilters(BaseModel):
	"""filters for listing events."""

	scope: EventScope | None = None
	thread_id: TypeID | None = None
	task_id: TypeID | None = None
	user_id: TypeID | None = None
	since: datetime | None = None


class EventBase(MetadataModel):
	"""shared event attributes."""

	scope: EventScope = EventScope.SYSTEM
	scope_id: TypeID | None = None
	type: str
	data: dict[str, Any] = Field(default_factory=dict)
	expires_at: datetime | None = None
	version: int = 1
	resource_revision: int | None = None
	user_id: TypeID | None = None
	thread_id: TypeID | None = None
	message_id: TypeID | None = None
	task_id: TypeID | None = None


class EventCreate(EventBase, ForbidExtraModel):
	"""payload to emit a new event."""

	pass


class Event(EventBase, TimestampedModel):
	"""event response."""

	id: TypeID


class EventsByMessageIDsRequest(MetadataModel, ForbidExtraModel):
	"""request payload to fetch events for a set of messages."""

	message_ids: list[TypeID] = Field(default_factory=list, max_length=500)
	limit: int = Field(default=500, ge=1, le=1000)
	cursor: str | None = None
	"""keyset cursor from a prior page's next_cursor."""


@dataclass(frozen=True)
class EventPage:
	"""one keyset page of event rows."""

	items: list[EventModel]
	"""page rows in (created_at, id) ascending order."""
	next_cursor: str | None = None
	"""cursor for the following page, or None at the end."""
	has_more: bool = False
