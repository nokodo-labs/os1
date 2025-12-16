"""Group schemas."""

from __future__ import annotations

from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from api.schemas.typeid import TypeID


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


class Group(GroupBase, TimestampedModel, ORMModel):
	"""Group schema."""

	id: TypeID
	owner_id: TypeID
