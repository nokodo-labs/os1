"""Reminder schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.reminder import ReminderStatus
from api.schemas.common import MetadataModel, ORMModel


class ReminderBase(MetadataModel):
	"""Base reminder schema."""

	content: str
	due_at: datetime
	recurrence: str | None = None
	status: ReminderStatus = ReminderStatus.PENDING
	notification_channels: list[str] = Field(default_factory=list)
	source_thread_id: str | None = None
	external_sync: dict[str, Any] | None = None


class ReminderCreate(ReminderBase):
	"""Schema for creating a reminder."""

	pass


class ReminderUpdate(ReminderBase):
	"""Schema for updating a reminder."""

	content: str | None = None
	due_at: datetime | None = None
	status: ReminderStatus | None = None


class Reminder(ReminderBase, ORMModel):
	"""Reminder schema."""

	id: str
	owner_id: int
