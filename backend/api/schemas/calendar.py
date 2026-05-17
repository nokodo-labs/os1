"""calendar schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from api.schemas.scheduled_item import Recurrence
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type CalendarSortBy = CommonSortBy | Literal["name", "position"]
type CalendarEventSortBy = CommonSortBy | Literal["start_at", "end_at", "title"]
type CalendarNotificationOffset = Annotated[int, Field(ge=0, le=525600)]


class CalendarListFilters(BaseModel):
	"""filters for listing calendars."""

	owner_id: TypeID | None = None


class CalendarEventListFilters(BaseModel):
	"""filters for listing calendar events."""

	start_at: datetime | None = None
	end_at: datetime | None = None
	q: str | None = Field(default=None, min_length=1, max_length=200)


class CalendarBase(MetadataModel):
	"""shared calendar fields."""

	name: str = Field(min_length=1, max_length=100)
	description: str | None = None
	color: str = Field(default="#d45446", min_length=4, max_length=7)
	position: float = 0.0
	is_default: bool = False
	timezone: str | None = Field(default=None, max_length=64)
	project_ids: list[TypeID] = Field(default_factory=list, max_length=100)


class CalendarCreate(CalendarBase):
	"""payload to create a calendar."""

	pass


class CalendarUpdate(MetadataUpdateModel):
	"""payload to update a calendar."""

	name: str | MissingType = Field(default=MISSING, min_length=1, max_length=100)
	description: str | None | MissingType = MISSING
	color: str | MissingType = Field(default=MISSING, min_length=4, max_length=7)
	position: float | MissingType = MISSING
	is_default: bool | MissingType = MISSING
	timezone: str | None | MissingType = Field(default=MISSING, max_length=64)
	project_ids: list[TypeID] | MissingType = Field(
		default=MISSING,
		max_length=100,
	)


class Calendar(CalendarBase, TimestampedModel):
	"""calendar response schema."""

	id: TypeID
	owner_id: TypeID


class CalendarEventBase(MetadataModel):
	"""shared calendar event fields."""

	title: str = Field(min_length=1, max_length=200)
	description: str | None = None
	start_at: datetime
	end_at: datetime
	all_day: bool = False
	timezone: str | None = Field(default=None, max_length=64)
	recurrence: Recurrence | None = None
	notification_offsets: list[CalendarNotificationOffset] = Field(
		default_factory=list,
		max_length=8,
	)
	location: str | None = Field(default=None, max_length=255)
	virtual_url: str | None = Field(default=None, max_length=512)
	labels: list[str] = Field(default_factory=list)

	@field_validator("notification_offsets")
	@classmethod
	def _normalize_notification_offsets(cls, value: list[int]) -> list[int]:
		return sorted(set(value))

	@model_validator(mode="after")
	def _validate_range(self) -> Self:
		if self.end_at <= self.start_at:
			raise ValueError("end time must be after start time")
		if self.location and self.virtual_url:
			raise ValueError("location and virtual url are mutually exclusive")
		return self


class CalendarEventCreate(CalendarEventBase):
	"""payload to create a calendar event."""

	pass


class CalendarEventUpdate(MetadataUpdateModel):
	"""payload to update a calendar event."""

	title: str | MissingType = Field(default=MISSING, min_length=1, max_length=200)
	description: str | None | MissingType = MISSING
	start_at: datetime | MissingType = MISSING
	end_at: datetime | MissingType = MISSING
	all_day: bool | MissingType = MISSING
	timezone: str | None | MissingType = Field(default=MISSING, max_length=64)
	recurrence: Recurrence | None | MissingType = MISSING
	notification_offsets: list[CalendarNotificationOffset] | MissingType = Field(
		default=MISSING,
		max_length=8,
	)
	location: str | None | MissingType = Field(default=MISSING, max_length=255)
	virtual_url: str | None | MissingType = Field(default=MISSING, max_length=512)
	labels: list[str] | MissingType = MISSING

	@field_validator("notification_offsets")
	@classmethod
	def _normalize_notification_offsets(
		cls,
		value: list[int],
	) -> list[int]:
		return sorted(set(value))

	@model_validator(mode="after")
	def _validate_place(self) -> Self:
		fields = self.model_fields_set
		if (
			"location" in fields
			and "virtual_url" in fields
			and self.location
			and self.virtual_url
		):
			raise ValueError("location and virtual url are mutually exclusive")
		return self


class CalendarEvent(CalendarEventBase, TimestampedModel):
	"""calendar event response schema."""

	id: TypeID
	owner_id: TypeID
	calendar_id: TypeID = Field(...)
	recurrence_until: datetime | None = None
	series_origin_id: TypeID | None = None
