"""scheduled item and recurrence schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from api.models.reminder import ReminderStatus
from nokodo_ai.utils.typeid import TypeID


type ScheduledItemKind = Literal["event", "reminder"]
type ScheduledEventStatus = Literal["scheduled", "cancelled"]


class Recurrence(BaseModel):
	"""structured recurrence value for schedule-capable masters."""

	rrule: list[str] = Field(
		default_factory=list,
		max_length=16,
		description=(
			"iCalendar RRULE lines. the field name follows the RRULE property "
			"name even though multiple lines are allowed."
		),
	)
	rdate: list[datetime] = Field(default_factory=list, max_length=256)
	exdate: list[datetime] = Field(default_factory=list, max_length=256)
	timezone: str | None = Field(default=None, max_length=64)

	@model_validator(mode="after")
	def _validate_not_empty(self) -> Self:
		if not self.rrule and not self.rdate:
			raise ValueError("recurrence requires at least one rrule or rdate")
		return self


class ScheduledItem(BaseModel):
	"""merged scheduled calendar/reminder instance."""

	kind: ScheduledItemKind
	id: str
	parent_id: TypeID
	container_id: TypeID
	original_occurrence_at: datetime
	effective_start_at: datetime
	effective_end_at: datetime | None = None
	all_day: bool = False
	title: str
	description: str | None = None
	color: str | None = None
	status: ScheduledEventStatus | ReminderStatus
	readonly: bool = False
	calendar_id: TypeID | None = None
	reminder_list_id: TypeID | None = None
	completed_at: datetime | None = None


class ScheduledItemListFilters(BaseModel):
	"""filters for listing merged scheduled items."""

	start_at: datetime
	end_at: datetime
	include_completed: bool = False


class ReminderOccurrenceComplete(BaseModel):
	"""payload to complete one reminder occurrence."""

	original_occurrence_at: datetime


class CalendarOccurrenceCancel(BaseModel):
	"""payload to cancel one event occurrence."""

	original_occurrence_at: datetime


class CalendarOccurrenceEdit(BaseModel):
	"""payload to edit one event occurrence."""

	original_occurrence_at: datetime
	new_start_at: datetime | None = None
	new_end_at: datetime | None = None
	title: str | None = Field(default=None, max_length=200)
	description: str | None = None
	location: str | None = Field(default=None, max_length=255)
	virtual_url: str | None = Field(default=None, max_length=512)


class CalendarSeriesEdit(CalendarOccurrenceEdit):
	"""payload to split and edit this and following event occurrences."""

	all_day: bool | None = None
	timezone: str | None = Field(default=None, max_length=64)
	recurrence: Recurrence | None = None
	notification_offsets: list[int] | None = Field(default=None, max_length=8)
	labels: list[str] | None = None

	@model_validator(mode="after")
	def _validate_place(self) -> Self:
		if self.location and self.virtual_url:
			raise ValueError("location and virtual url are mutually exclusive")
		return self


class ReminderSeriesEdit(BaseModel):
	"""payload to split and edit this and following reminder occurrences."""

	original_occurrence_at: datetime
	title: str | None = Field(default=None, max_length=200)
	description: str | None = None
	due_at: datetime | None = None
	remind_at: datetime | None = None
	recurrence: Recurrence | None = None
	position: float | None = None
