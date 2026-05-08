"""scheduled item and recurrence schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from pydantic import BaseModel, Field, field_validator, model_validator

from api.models.reminder import ReminderStatus
from api.schemas.common import MISSING, MissingType
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

	@field_validator("rrule")
	@classmethod
	def _validate_rrules(cls, value: list[str]) -> list[str]:
		validated: list[str] = []
		for rule in value:
			trimmed = rule.strip()
			if not trimmed:
				raise ValueError("rrule entries cannot be empty")
			try:
				rrulestr(_normalize_rrule(trimmed), dtstart=datetime.now(tz=UTC))
			except (TypeError, ValueError) as exc:
				raise ValueError(f"invalid rrule: {trimmed}") from exc
			validated.append(trimmed)
		return validated

	@field_validator("timezone")
	@classmethod
	def _validate_timezone(cls, value: str | None) -> str | None:
		if value is None:
			return None
		trimmed = value.strip()
		if not trimmed:
			return None
		try:
			ZoneInfo(trimmed)
		except ZoneInfoNotFoundError as exc:
			raise ValueError(f"invalid timezone: {trimmed}") from exc
		return trimmed

	@model_validator(mode="after")
	def _validate_not_empty(self) -> Self:
		if not self.rrule and not self.rdate:
			raise ValueError("recurrence requires at least one rrule or rdate")
		return self


def _normalize_rrule(rule_text: str) -> str:
	rule = rule_text.strip()
	return rule if rule.upper().startswith("RRULE:") else f"RRULE:{rule}"


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
	new_start_at: datetime | None | MissingType = MISSING
	new_end_at: datetime | None | MissingType = MISSING
	title: str | MissingType = Field(default=MISSING, max_length=200)
	description: str | None | MissingType = MISSING
	location: str | None | MissingType = Field(default=MISSING, max_length=255)
	virtual_url: str | None | MissingType = Field(default=MISSING, max_length=512)


class CalendarSeriesEdit(CalendarOccurrenceEdit):
	"""payload to split and edit this and following event occurrences."""

	all_day: bool | MissingType = MISSING
	timezone: str | None | MissingType = Field(default=MISSING, max_length=64)
	recurrence: Recurrence | None | MissingType = MISSING
	notification_offsets: list[int] | MissingType = Field(
		default=MISSING,
		max_length=8,
	)
	labels: list[str] | MissingType = MISSING

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


class ReminderSeriesEdit(BaseModel):
	"""payload to split and edit this and following reminder occurrences."""

	original_occurrence_at: datetime
	title: str | MissingType = Field(default=MISSING, max_length=200)
	description: str | None | MissingType = MISSING
	due_at: datetime | None | MissingType = MISSING
	remind_at: datetime | None | MissingType = MISSING
	recurrence: Recurrence | None | MissingType = MISSING
	position: float | MissingType = MISSING
