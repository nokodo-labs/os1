"""reminder models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.many_to_many import reminder_list_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.types import JSONObject
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.event import Event
	from api.models.project import Project
	from api.models.thread import Thread
	from api.models.user import User


class ReminderStatus(StrEnum):
	"""status of a reminder."""

	PENDING = "pending"
	COMPLETED = "completed"


class ReminderList(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	Base,
):
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
		Index("ix_reminder_lists_owner_default", "owner_id", "is_default"),
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
	is_default: Mapped[bool] = mapped_column(Boolean, default=False)

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
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="reminder_list",
	)


class Reminder(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	Base,
):
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
	list_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id", ondelete="CASCADE"),
	)
	parent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id", ondelete="CASCADE"),
	)
	source_thread_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id"),
	)

	title: Mapped[str] = mapped_column(String(200))
	description: Mapped[str | None] = mapped_column(Text)
	due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	recurrence: Mapped[JSONObject | None] = mapped_column(JSONB)
	recurrence_until: Mapped[datetime | None] = mapped_column(
		DateTime(timezone=True),
		index=True,
	)
	series_origin_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id"),
	)
	status: Mapped[ReminderStatus] = mapped_column(
		StringEnum(ReminderStatus),
		default=ReminderStatus.PENDING,
	)
	completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	position: Mapped[float] = mapped_column(Float, default=0.0)

	owner: Mapped[User] = relationship("User", back_populates="reminders")
	reminder_list: Mapped[ReminderList] = relationship(
		"ReminderList",
		back_populates="reminders",
	)
	series_origin: Mapped[Reminder | None] = relationship(
		"Reminder",
		remote_side="Reminder.id",
		foreign_keys=[series_origin_id],
	)
	thread: Mapped[Thread | None] = relationship("Thread")
	parent: Mapped[Reminder | None] = relationship(
		"Reminder",
		back_populates="subtasks",
		remote_side="Reminder.id",
		foreign_keys=[parent_id],
	)
	subtasks: Mapped[list[Reminder]] = relationship(
		"Reminder",
		back_populates="parent",
		lazy="noload",
		cascade="all, delete-orphan",
		foreign_keys=[parent_id],
	)
	overrides: Mapped[list[ReminderOverride]] = relationship(
		"ReminderOverride",
		back_populates="reminder",
		cascade="all, delete-orphan",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="reminder",
	)


class ReminderOverride(TimestampMixin, Base):
	"""single reminder occurrence override."""

	__tablename__ = "reminder_overrides"
	__table_args__ = (
		Index(
			"ix_reminder_overrides_reminder_original",
			"reminder_id",
			"original_occurrence_at",
		),
	)

	reminder_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("reminders.id", ondelete="CASCADE"),
		primary_key=True,
	)
	original_occurrence_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		primary_key=True,
	)
	completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

	reminder: Mapped[Reminder] = relationship(
		"Reminder",
		back_populates="overrides",
	)
