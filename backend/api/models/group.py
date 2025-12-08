"""Group model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import (
	MetadataJSONMixin,
	StringEnum,
	TimestampMixin,
	UUIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.acl import AccessControlEntry
	from api.models.user import User


class GroupMemberRole(StrEnum):
	"""Role of a user in a group."""

	OWNER = "owner"
	ADMIN = "admin"
	MEMBER = "member"


class GroupMembership(UUIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""Association model for users participating in groups."""

	__tablename__ = "group_memberships"

	group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

	group: Mapped[Group] = relationship("Group", back_populates="memberships")
	user: Mapped[User] = relationship("User", back_populates="group_memberships")
	role: Mapped[GroupMemberRole] = mapped_column(
		StringEnum(GroupMemberRole),
		default=GroupMemberRole.MEMBER,
	)


class Group(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Group model for user collaboration."""

	__tablename__ = "groups"

	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

	owner: Mapped[User] = relationship("User", back_populates="owned_groups")
	memberships: Mapped[list[GroupMembership]] = relationship(
		"GroupMembership", back_populates="group", cascade="all, delete-orphan"
	)
	access_control_entries: Mapped[list[AccessControlEntry]] = relationship(
		"AccessControlEntry", back_populates="group", cascade="all, delete-orphan"
	)
