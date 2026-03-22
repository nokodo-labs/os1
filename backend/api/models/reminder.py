"""reminder models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.many_to_many import reminder_list_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.project import Project
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
	__table_args__ = (
		Index(
			"idx_reminder_lists_name_trgm",
			"name",
			postgresql_using="gin",
			postgresql_ops={"name": "gin_trgm_ops"},
		),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	color: Mapped[str | None] = mapped_column(String(7))  # hex color e.g. #FF5733
	icon: Mapped[str | None] = mapped_column(String(50))  # emoji or icon name
	position: Mapped[float] = mapped_column(Float, default=0.0)

	owner: Mapped[User] = relationship("User", back_populates="reminder_lists")
	projects: Mapped[list[Project]] = relationship(
		"Project",
		secondary=reminder_list_project_association,
		back_populates="reminder_lists",
	)

	@property
	def project_ids(self) -> list[TypeID]:
		"""IDs of linked projects (requires projects to be loaded)."""
		return [p.id for p in self.projects]

	reminders: Mapped[list[Reminder]] = relationship(
		"Reminder",
		back_populates="reminder_list",
		cascade="all, delete-orphan",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="reminder_list",
		cascade="all, delete-orphan",
	)


class Reminder(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""reminder model."""

	__tablename__ = "reminders"
	__typeid_prefix__ = "rem"
	__table_args__ = (
		Index(
			"idx_reminders_title_trgm",
			"title",
			postgresql_using="gin",
			postgresql_ops={"title": "gin_trgm_ops"},
		),
		Index(
			"idx_reminders_description_trgm",
			"description",
			postgresql_using="gin",
			postgresql_ops={"description": "gin_trgm_ops"},
		),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	list_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id"),
	)
	parent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id"),
	)
	source_thread_id: Mapped[TypeID | None] = mapped_column(
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
	reminder_list: Mapped[ReminderList | None] = relationship(
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
		lazy="noload",
		cascade="all, delete-orphan",
	)
