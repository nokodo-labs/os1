"""Access Control Entry model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.group import Group
	from api.models.project import Project
	from api.models.thread import Thread
	from api.models.user import User


class AccessRole(StrEnum):
	"""Level of access granted."""

	VIEWER = "viewer"
	EDITOR = "editor"
	ADMIN = "admin"


class AccessControlEntry(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Generic sharing primitive that grants principals access to resources."""

	__tablename__ = "access_control_entries"

	# Resources (one nullable FK per resource type)
	thread_id: Mapped[str | None] = mapped_column(
		ForeignKey("threads.id", ondelete="CASCADE"), index=True
	)
	project_id: Mapped[str | None] = mapped_column(
		ForeignKey("projects.id", ondelete="CASCADE"), index=True
	)

	# Principals (one nullable FK per principal type)
	user_id: Mapped[int | None] = mapped_column(
		ForeignKey("users.id", ondelete="CASCADE"), index=True
	)
	group_id: Mapped[str | None] = mapped_column(
		ForeignKey("groups.id", ondelete="CASCADE"), index=True
	)
	agent_id: Mapped[str | None] = mapped_column(
		ForeignKey("agents.id", ondelete="CASCADE"), index=True
	)

	role: Mapped[AccessRole] = mapped_column(
		Enum(AccessRole, name="access_role"), default=AccessRole.VIEWER
	)

	# Relationships
	thread: Mapped[Thread | None] = relationship(
		"Thread", back_populates="access_control_entries"
	)
	project: Mapped[Project | None] = relationship(
		"Project", back_populates="access_control_entries"
	)

	user: Mapped[User | None] = relationship(
		"User", back_populates="access_control_entries"
	)
	group: Mapped[Group | None] = relationship(
		"Group", back_populates="access_control_entries"
	)
	agent: Mapped[Agent | None] = relationship(
		"Agent", back_populates="access_control_entries"
	)
