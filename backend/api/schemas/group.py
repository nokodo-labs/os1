"""Group schemas."""

from __future__ import annotations

from api.models.group import GroupMemberRole
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class GroupBase(MetadataModel):
	"""Base group schema."""

	name: str
	description: str | None = None


class GroupCreate(GroupBase):
	"""Schema for creating a group."""

	pass


class GroupUpdate(GroupBase):
	"""Schema for updating a group."""

	name: str | None = None
	description: str | None = None


class GroupMembershipResponse(ORMModel):
	"""Schema for a group membership."""

	id: TypeID
	user_id: TypeID
	role: GroupMemberRole


class GroupMembershipCreate(ORMModel):
	"""Schema for adding a member to a group."""

	user_id: TypeID
	role: GroupMemberRole = GroupMemberRole.MEMBER


class Group(GroupBase, TimestampedModel, ORMModel):
	"""Group schema."""

	id: TypeID
	owner_id: TypeID
	memberships: list[GroupMembershipResponse] = []
