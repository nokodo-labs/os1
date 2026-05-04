"""event model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.calendar import Calendar, CalendarEvent
	from api.models.message import Message
	from api.models.notification import Notification
	from api.models.project import Project
	from api.models.reminder import Reminder, ReminderList
	from api.models.task import Task
	from api.models.thread import Thread
	from api.models.user import User


class EventScope(StrEnum):
	"""domain scopes for events."""

	SYSTEM = "system"
	USER = "user"
	THREAD = "thread"
	MESSAGE = "message"
	TASK = "task"
	PROJECT = "project"
	FILE = "file"


class Event(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""universal event record powering live updates and replay."""

	__tablename__ = "events"
	__typeid_prefix__ = "event"

	scope: Mapped[EventScope] = mapped_column(
		StringEnum(EventScope),
		default=EventScope.SYSTEM,
	)
	scope_id: Mapped[TypeID | None] = mapped_column(String(TYPEID_LENGTH))
	type: Mapped[str] = mapped_column(String(100))
	data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
	expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	version: Mapped[int] = mapped_column(Integer(), default=1)
	user_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="SET NULL"),
		index=True,
	)
	thread_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="SET NULL"),
		index=True,
	)
	message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
	)
	task_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("tasks.id", ondelete="SET NULL"),
	)
	project_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="SET NULL"),
	)
	calendar_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendars.id", ondelete="SET NULL"),
		index=True,
	)
	calendar_event_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("calendar_events.id", ondelete="SET NULL"),
		index=True,
	)
	reminder_list_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id", ondelete="SET NULL"),
		index=True,
	)
	reminder_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id", ondelete="SET NULL"),
		index=True,
	)

	user: Mapped[User | None] = relationship("User")
	thread: Mapped[Thread | None] = relationship(
		"Thread",
		back_populates="events",
	)
	message: Mapped[Message | None] = relationship(
		"Message",
		back_populates="events",
	)
	task: Mapped[Task | None] = relationship(
		"Task",
		back_populates="events",
	)
	project: Mapped[Project | None] = relationship(
		"Project",
		back_populates="events",
	)
	calendar: Mapped[Calendar | None] = relationship(
		"Calendar",
		back_populates="activity_events",
	)
	calendar_event: Mapped[CalendarEvent | None] = relationship(
		"CalendarEvent",
		back_populates="events",
	)
	reminder_list: Mapped[ReminderList | None] = relationship(
		"ReminderList",
		back_populates="events",
	)
	reminder: Mapped[Reminder | None] = relationship(
		"Reminder",
		back_populates="events",
	)
	notifications: Mapped[list[Notification]] = relationship(
		"Notification",
		back_populates="event",
		cascade="all, delete-orphan",
	)
