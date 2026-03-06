"""Group model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.user import User


class GroupMemberRole(StrEnum):
	"""Role of a user in a group."""

	OWNER = "owner"
	ADMIN = "admin"
	MEMBER = "member"


class GroupMembership(TypeIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""Association model for users participating in groups."""

	__tablename__ = "group_memberships"
	__typeid_prefix__ = "gmem"

	group_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("groups.id", ondelete="CASCADE"),
	)
	user_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
	)

	group: Mapped[Group] = relationship("Group", back_populates="memberships")
	user: Mapped[User] = relationship("User", back_populates="group_memberships")
	role: Mapped[GroupMemberRole] = mapped_column(
		StringEnum(GroupMemberRole),
		default=GroupMemberRole.MEMBER,
	)


class Group(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Group model for user collaboration."""

	__tablename__ = "groups"
	__typeid_prefix__ = "group"

	name: Mapped[str] = mapped_column(String(100))
	description: Mapped[str | None] = mapped_column(String(500))
	owner_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)

	owner: Mapped[User] = relationship("User", back_populates="owned_groups")
	memberships: Mapped[list[GroupMembership]] = relationship(
		"GroupMembership",
		back_populates="group",
		cascade="all, delete-orphan",
	)

	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		foreign_keys="AccessRule.subject_group_id",
		cascade="all, delete-orphan",
		overlaps="subject_group",
	)
	resource_access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		foreign_keys="AccessRule.group_id",
		cascade="all, delete-orphan",
		overlaps="group",
	)
