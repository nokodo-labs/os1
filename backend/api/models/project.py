"""project model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import (
	calendar_project_association,
	file_project_association,
	note_project_association,
	reminder_list_project_association,
	thread_project_association,
)
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.calendar import Calendar
	from api.models.event import Event
	from api.models.file import File
	from api.models.note import Note
	from api.models.reminder import ReminderList
	from api.models.thread import Thread
	from api.models.user import User


class Project(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""project model for organizing resources."""

	__tablename__ = "projects"
	__typeid_prefix__ = "proj"

	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)

	owner: Mapped[User] = relationship("User", back_populates="projects")
	threads: Mapped[list[Thread]] = relationship(
		"Thread",
		secondary=thread_project_association,
		back_populates="projects",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="project",
		cascade="all, delete-orphan",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="project",
		cascade="all, delete-orphan",
	)
	files: Mapped[list[File]] = relationship(
		"File",
		secondary=file_project_association,
		back_populates="projects",
	)
	notes: Mapped[list[Note]] = relationship(
		"Note",
		secondary=note_project_association,
		back_populates="projects",
	)
	reminder_lists: Mapped[list[ReminderList]] = relationship(
		"ReminderList",
		secondary=reminder_list_project_association,
		back_populates="projects",
	)
	calendars: Mapped[list[Calendar]] = relationship(
		"Calendar",
		secondary=calendar_project_association,
		back_populates="projects",
	)

	@property
	def thread_ids(self) -> list[TypeID]:
		if "threads" not in self.__dict__:
			return []
		return [thread.id for thread in self.threads if thread.id]
