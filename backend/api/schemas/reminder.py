"""reminder schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.models.reminder import ReminderStatus
from api.schemas.common import MetadataModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


# --- ReminderList schemas ---


class ReminderListBase(MetadataModel):
	"""base reminder list schema."""

	name: str = Field(max_length=100)
	description: str | None = Field(default=None, max_length=500)
	color: str | None = Field(default=None, max_length=7)
	icon: str | None = Field(default=None, max_length=50)
	position: float = 0.0
	project_id: TypeID | None = None


class ReminderListCreate(ReminderListBase):
	"""schema for creating a reminder list."""

	pass


class ReminderListUpdate(MetadataModel):
	"""schema for updating a reminder list."""

	name: str | None = Field(default=None, max_length=100)
	description: str | None = Field(default=None, max_length=500)
	color: str | None = None
	icon: str | None = None
	position: float | None = None
	project_id: TypeID | None = None


class ReminderList(ReminderListBase, TimestampedModel):
	"""reminder list response schema."""

	id: TypeID
	owner_id: TypeID


class ReminderListWithCounts(ReminderList):
	"""reminder list with reminder counts."""

	total_count: int = 0
	pending_count: int = 0
	completed_count: int = 0


# --- Reminder schemas ---


class ReminderBase(MetadataModel):
	"""base reminder schema."""

	title: str = Field(max_length=200)
	description: str | None = None
	due_at: datetime | None = None
	remind_at: datetime | None = None
	recurrence: str | None = Field(default=None, max_length=255)
	status: ReminderStatus = ReminderStatus.PENDING
	list_id: TypeID | None = None
	parent_id: TypeID | None = None
	source_thread_id: TypeID | None = None
	position: float = 0.0


class ReminderCreate(ReminderBase):
	"""schema for creating a reminder."""

	pass


class ReminderUpdate(MetadataModel):
	"""schema for updating a reminder."""

	title: str | None = Field(default=None, max_length=200)
	description: str | None = None
	due_at: datetime | None = None
	remind_at: datetime | None = None
	recurrence: str | None = None
	status: ReminderStatus | None = None
	completed_at: datetime | None = None
	list_id: TypeID | None = None
	parent_id: TypeID | None = None
	position: float | None = None


class Reminder(ReminderBase, TimestampedModel):
	"""reminder response schema."""

	id: TypeID
	owner_id: TypeID
	completed_at: datetime | None = None


class ReminderWithSubtasks(Reminder):
	"""reminder with nested subtasks."""

	subtasks: list[Reminder] = Field(default_factory=list)
