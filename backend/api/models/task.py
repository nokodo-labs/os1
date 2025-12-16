"""Task model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import (
	TYPEID_LENGTH,
	MetadataJSONMixin,
	StringEnum,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.event import Event
	from api.models.message import Message
	from api.models.thread import Thread
	from api.models.user import User


class TaskStatus(StrEnum):
	"""Lifecycle status for long-running operations."""

	PENDING = "pending"
	RUNNING = "running"
	COMPLETED = "complete"
	FAILED = "failed"
	CANCELLED = "cancelled"


class TaskType(StrEnum):
	"""High-level task categories."""

	CODE_SESSION = "code_session"
	RESEARCH = "research"
	IMAGE = "image_generation"
	CUSTOM = "custom"


class Task(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Represents independent work that can outlive threads."""

	__tablename__ = "tasks"
	__typeid_prefix__ = "task"

	user_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	task_type: Mapped[TaskType] = mapped_column(
		StringEnum(TaskType),
		default=TaskType.CUSTOM,
	)
	status: Mapped[TaskStatus] = mapped_column(
		StringEnum(TaskStatus),
		default=TaskStatus.PENDING,
	)
	progress: Mapped[int | None] = mapped_column(Integer())
	stage: Mapped[str | None] = mapped_column(String(100))
	result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	spawned_thread_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="SET NULL"),
	)
	started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_event_at: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		onupdate=func.now(),
	)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="tasks",
		innerjoin=True,
	)
	spawned_thread: Mapped[Thread | None] = relationship(
		"Thread",
		back_populates="tasks",
	)
	messages: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="task",
		foreign_keys="Message.task_id",
		primaryjoin="Message.task_id == Task.id",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="task",
	)
