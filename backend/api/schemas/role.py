"""role schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from api.models.permissions import DefaultPermissions
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class RoleBase(MetadataModel):
	"""base role schema."""

	name: str
	description: str | None = None
	quotas: dict[str, Any] = Field(default_factory=dict)
	priority: int = 0
	default_permissions: DefaultPermissions = Field(default_factory=DefaultPermissions)


class RoleCreate(RoleBase):
	"""schema for creating a role."""


class RoleUpdate(ORMModel):
	"""schema for updating a role."""

	name: str | None = None
	description: str | None = None
	quotas: dict[str, Any] | None = None
	priority: int | None = None
	default_permissions: DefaultPermissions | None = None


class Role(RoleBase, TimestampedModel, ORMModel):
	"""role response schema."""

	id: TypeID
