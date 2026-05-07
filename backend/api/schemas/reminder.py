"""reminder schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.reminder import ReminderStatus
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from api.schemas.scheduled_item import Recurrence
from nokodo_ai.utils.typeid import TypeID


type ReminderSortBy = Literal[
	"position",
	"due_at",
	"created_at",
	"updated_at",
	"title",
]
type ReminderListSortBy = Literal["position", "name", "created_at", "updated_at"]


class ReminderListItemFilters(BaseModel):
	"""filters for listing reminders in a list."""

	status_filter: ReminderStatus | None = None


class ScheduledReminderListFilters(BaseModel):
	"""filters for listing scheduled reminders."""

	status_filter: ReminderStatus | None = ReminderStatus.PENDING


# ReminderList schemas


class ReminderListBase(MetadataModel):
	"""base reminder list schema."""

	name: str = Field(max_length=100)
	description: str | None = Field(default=None, max_length=500)
	color: str | None = Field(default=None, max_length=7)
	icon: str | None = Field(default=None, max_length=50)
	position: float = 0.0
	is_default: bool = False
	project_ids: list[TypeID] = Field(default_factory=list)


class ReminderListCreate(ReminderListBase):
	"""schema for creating a reminder list."""

	pass


class ReminderListUpdate(MetadataUpdateModel):
	"""schema for updating a reminder list."""

	name: str | MissingType = Field(default=MISSING, max_length=100)
	description: str | None | MissingType = Field(default=MISSING, max_length=500)
	color: str | None | MissingType = MISSING
	icon: str | None | MissingType = MISSING
	position: float | MissingType = MISSING
	is_default: bool | MissingType = MISSING
	project_ids: list[TypeID] | MissingType = MISSING


class ReminderList(ReminderListBase, TimestampedModel):
	"""reminder list response schema."""

	id: TypeID
	owner_id: TypeID


class ReminderListWithCounts(ReminderList):
	"""reminder list with reminder counts."""

	total_count: int = 0
	pending_count: int = 0
	completed_count: int = 0


# Reminder schemas


class ReminderBase(MetadataModel):
	"""base reminder schema."""

	title: str = Field(max_length=200)
	description: str | None = None
	due_at: datetime | None = None
	remind_at: datetime | None = None
	recurrence: Recurrence | None = None
	status: ReminderStatus = ReminderStatus.PENDING
	parent_id: TypeID | None = None
	source_thread_id: TypeID | None = None
	position: float = 0.0


class ReminderCreate(ReminderBase):
	"""schema for creating a reminder."""

	list_id: TypeID | None = None


class ReminderUpdate(MetadataUpdateModel):
	"""schema for updating a reminder."""

	title: str | MissingType = Field(default=MISSING, max_length=200)
	description: str | None | MissingType = MISSING
	due_at: datetime | None | MissingType = MISSING
	remind_at: datetime | None | MissingType = MISSING
	recurrence: Recurrence | None | MissingType = MISSING
	status: ReminderStatus | MissingType = MISSING
	list_id: TypeID | MissingType = MISSING
	parent_id: TypeID | None | MissingType = MISSING
	position: float | MissingType = MISSING


class Reminder(ReminderBase, TimestampedModel):
	"""reminder response schema."""

	id: TypeID
	owner_id: TypeID
	list_id: TypeID
	completed_at: datetime | None = None
	recurrence_until: datetime | None = None
	series_origin_id: TypeID | None = None


class ReminderWithSubtasks(Reminder):
	"""reminder with nested subtasks."""

	subtasks: list[Reminder] = Field(default_factory=list)
