"""role schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from api.permissions import DefaultPermissions
from api.schemas.common import (
	MetadataModel,
	MetadataUpdateModel,
	ORMModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type RoleSortBy = CommonSortBy | Literal["priority", "name"]


class RoleListFilters(BaseModel):
	"""filters for listing roles."""

	user_id: TypeID | None = None


class RoleBase(MetadataModel):
	"""base role schema."""

	name: str
	description: str | None = None
	quotas: dict[str, Any] = Field(default_factory=dict)
	priority: int = 0
	default_permissions: DefaultPermissions = Field(default_factory=DefaultPermissions)


class RoleCreate(RoleBase):
	"""schema for creating a role."""

	# inherits priority: int = 0 from RoleBase


class RoleUpdate(MetadataUpdateModel):
	"""schema for updating a role."""

	name: str | None = None
	description: str | None = None
	quotas: dict[str, Any] | None = None
	priority: int | None = None
	default_permissions: DefaultPermissions | None = None


class Role(RoleBase, TimestampedModel, ORMModel):
	"""role response schema."""

	id: TypeID
