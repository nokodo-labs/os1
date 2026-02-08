"""user model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base
from api.models.many_to_many import user_role_association
from api.models.mixins import TypeIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.file import File
	from api.models.group import Group, GroupMembership
	from api.models.memory import Memory
	from api.models.note import Note
	from api.models.notification import Notification
	from api.models.project import Project
	from api.models.reminder import Reminder, ReminderList
	from api.models.role import Role
	from api.models.task import Task
	from api.models.thread import Thread
	from api.models.thread_participant import ThreadParticipant


class User(TypeIDPrimaryKeyMixin, Base):
	"""User model."""

	__tablename__ = "users"
	__typeid_prefix__ = "user"

	email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
	display_name: Mapped[str | None] = mapped_column(String(150))
	avatar_url: Mapped[str | None] = mapped_column(String(512))
	hashed_password: Mapped[str] = mapped_column(String(255))
	is_active: Mapped[bool] = mapped_column(default=True)
	is_superuser: Mapped[bool] = mapped_column(default=False)
	preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	integration_tokens: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	usage_quotas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now()
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
	)

	roles: Mapped[list[Role]] = relationship(
		"Role",
		secondary=user_role_association,
		back_populates="users",
	)

	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		foreign_keys="AccessRule.subject_user_id",
		cascade="all, delete-orphan",
		overlaps="subject_user",
	)
	projects: Mapped[list[Project]] = relationship("Project", back_populates="owner")
	owned_groups: Mapped[list[Group]] = relationship("Group", back_populates="owner")
	group_memberships: Mapped[list[GroupMembership]] = relationship(
		"GroupMembership",
		back_populates="user",
		cascade="all, delete-orphan",
	)
	reminders: Mapped[list[Reminder]] = relationship("Reminder", back_populates="owner")
	reminder_lists: Mapped[list[ReminderList]] = relationship(
		"ReminderList",
		back_populates="owner",
		cascade="all, delete-orphan",
	)

	threads: Mapped[list[Thread]] = relationship(
		"Thread",
		back_populates="owner",
		cascade="all, delete-orphan",
	)
	tasks: Mapped[list[Task]] = relationship(
		"Task",
		back_populates="owner",
		cascade="all, delete-orphan",
	)
	notifications: Mapped[list[Notification]] = relationship(
		"Notification",
		back_populates="user",
		cascade="all, delete-orphan",
	)
	memories: Mapped[list[Memory]] = relationship(
		"Memory",
		back_populates="owner",
		cascade="all, delete-orphan",
	)
	notes: Mapped[list[Note]] = relationship(
		"Note",
		back_populates="owner",
		cascade="all, delete-orphan",
	)
	files: Mapped[list[File]] = relationship(
		"File",
		back_populates="owner",
		cascade="all, delete-orphan",
	)
	thread_participants: Mapped[list[ThreadParticipant]] = relationship(
		"ThreadParticipant",
		back_populates="user",
		cascade="all, delete-orphan",
	)
