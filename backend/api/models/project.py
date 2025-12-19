"""Project model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import thread_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.acl import AccessControlEntry
	from api.models.event import Event
	from api.models.file import File
	from api.models.thread import Thread
	from api.models.user import User


class Project(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Project model for organizing resources."""

	__tablename__ = "projects"
	__typeid_prefix__ = "proj"

	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	owner_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)

	owner: Mapped[User] = relationship("User", back_populates="projects")
	threads: Mapped[list[Thread]] = relationship(
		"Thread",
		secondary=thread_project_association,
		back_populates="projects",
	)
	access_control_entries: Mapped[list[AccessControlEntry]] = relationship(
		"AccessControlEntry",
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
		back_populates="project",
	)
