"""Thread model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	JSON,
	DateTime,
	ForeignKey,
	String,
	func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.acl import AccessControlEntry
	from api.models.event import Event
	from api.models.memory import Memory
	from api.models.message import Message
	from api.models.project import Project
	from api.models.task import Task
	from api.models.user import User


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Conversation container tying together messages, events, and tasks."""

	__tablename__ = "threads"

	title: Mapped[str | None] = mapped_column(String(255), nullable=True)
	tags: Mapped[list[str]] = mapped_column(JSON, default=list)
	is_archived: Mapped[bool] = mapped_column(default=False)
	last_activity_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
		onupdate=func.now(),
	)

	owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
	project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))

	owner: Mapped[User] = relationship(
		"User",
		back_populates="threads",
		innerjoin=True,
	)
	project: Mapped[Project | None] = relationship("Project", back_populates="threads")
	access_control_entries: Mapped[list[AccessControlEntry]] = relationship(
		"AccessControlEntry",
		back_populates="thread",
		cascade="all, delete-orphan",
	)
	messages: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	tasks: Mapped[list[Task]] = relationship(
		"Task",
		back_populates="spawned_thread",
	)
	memories: Mapped[list[Memory]] = relationship(
		"Memory",
		back_populates="thread",
	)
