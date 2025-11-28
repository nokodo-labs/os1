"""Reminder model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.thread import Thread
	from api.models.user import User


class ReminderStatus(StrEnum):
	"""Status of a reminder."""

	PENDING = "pending"
	TRIGGERED = "triggered"
	DISMISSED = "dismissed"
	SNOOZED = "snoozed"


class Reminder(UUIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""Reminder model."""

	__tablename__ = "reminders"

	owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	content: Mapped[str] = mapped_column(String(500))
	due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	recurrence: Mapped[str | None] = mapped_column(String(50))
	status: Mapped[ReminderStatus] = mapped_column(
		Enum(ReminderStatus), default=ReminderStatus.PENDING
	)
	notification_channels: Mapped[list[str]] = mapped_column(JSON, default=list)
	source_thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id"))
	external_sync: Mapped[dict[str, Any] | None] = mapped_column(JSON)

	owner: Mapped[User] = relationship("User", back_populates="reminders")
	thread: Mapped[Thread | None] = relationship("Thread")
