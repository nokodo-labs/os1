"""group schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from api.models.group import GroupMemberRole
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type GroupSortBy = CommonSortBy | Literal["name"]


class GroupListFilters(BaseModel):
	"""filters for listing groups."""

	user_id: TypeID | None = None


class GroupBase(MetadataModel):
	"""base group schema."""

	name: str
	description: str | None = None


class GroupCreate(GroupBase):
	"""schema for creating a group."""

	pass


class GroupUpdate(MetadataUpdateModel):
	"""schema for updating a group."""

	name: str | MissingType = MISSING
	description: str | None | MissingType = MISSING


class GroupMembershipResponse(ORMModel):
	"""schema for a group membership."""

	id: TypeID
	user_id: TypeID
	role: GroupMemberRole


class GroupMembershipCreate(ORMModel):
	"""schema for adding a member to a group."""

	user_id: TypeID
	role: GroupMemberRole = GroupMemberRole.MEMBER


class Group(GroupBase, TimestampedModel, ORMModel):
	"""group schema."""

	id: TypeID
	owner_id: TypeID
	memberships: list[GroupMembershipResponse] = []
