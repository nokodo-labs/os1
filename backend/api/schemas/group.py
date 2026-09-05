"""group schemas."""

from typing import Literal

from api.models.group import GroupMemberRole
from api.schemas.access_rule import ResourceAccessListFilters
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type GroupSortBy = CommonSortBy | Literal["name"]


class GroupListFilters(ResourceAccessListFilters):
	"""filters for listing groups."""

	owner_id: TypeID | None = None
	member_user_id: TypeID | None = None
	q: str | None = None


class GroupBase(MetadataModel):
	"""base group schema."""

	name: str
	description: str | None = None


class GroupCreate(GroupBase, ForbidExtraModel):
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


class GroupMembershipCreate(ForbidExtraModel):
	"""schema for adding a member to a group."""

	user_id: TypeID
	role: GroupMemberRole = GroupMemberRole.MEMBER


class Group(GroupBase, TimestampedModel, ORMModel):
	"""group schema."""

	id: TypeID
	owner_id: TypeID
	memberships: list[GroupMembershipResponse] = []


class GroupSummary(ORMModel):
	"""minimal group identity for embedding (e.g. thread participants)."""

	id: TypeID
	name: str
