"""reminder models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.thread import Thread
	from api.models.user import User


class ReminderStatus(StrEnum):
	"""status of a reminder."""

	PENDING = "pending"
	COMPLETED = "completed"


class ReminderList(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""reminder list model for grouping reminders."""

	__tablename__ = "reminder_lists"
	__typeid_prefix__ = "reml"

	owner_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	color: Mapped[str | None] = mapped_column(String(7))  # hex color e.g. #FF5733
	icon: Mapped[str | None] = mapped_column(String(50))  # emoji or icon name
	position: Mapped[float] = mapped_column(Float, default=0.0)

	owner: Mapped[User] = relationship("User", back_populates="reminder_lists")
	reminders: Mapped[list[Reminder]] = relationship(
		"Reminder",
		back_populates="list",
		cascade="all, delete-orphan",
	)


class Reminder(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""reminder model."""

	__tablename__ = "reminders"
	__typeid_prefix__ = "rem"

	owner_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	list_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id"),
	)
	parent_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id"),
	)
	source_thread_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id"),
	)

	title: Mapped[str] = mapped_column(String(200))
	description: Mapped[str | None] = mapped_column(Text)
	due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	recurrence: Mapped[str | None] = mapped_column(String(255))  # rrule string
	status: Mapped[ReminderStatus] = mapped_column(
		StringEnum(ReminderStatus),
		default=ReminderStatus.PENDING,
	)
	completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	position: Mapped[float] = mapped_column(Float, default=0.0)

	owner: Mapped[User] = relationship("User", back_populates="reminders")
	list: Mapped[ReminderList | None] = relationship(
		"ReminderList",
		back_populates="reminders",
	)
	thread: Mapped[Thread | None] = relationship("Thread")
	parent: Mapped[Reminder | None] = relationship(
		"Reminder",
		back_populates="subtasks",
		remote_side="Reminder.id",
	)
	subtasks: Mapped[list[Reminder]] = relationship(
		"Reminder",
		back_populates="parent",
		cascade="all, delete-orphan",
	)
