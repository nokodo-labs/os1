"""Role schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from api.schemas.common import MetadataModel, ORMModel


class RoleBase(MetadataModel):
	"""Base role schema."""

	name: str
	permissions: list[str] = Field(default_factory=list)
	quotas: dict[str, Any] = Field(default_factory=dict)
	priority: int = 0


class RoleCreate(RoleBase):
	"""Schema for creating a role."""

	pass


class RoleUpdate(RoleBase):
	"""Schema for updating a role."""

	name: str | None = None


class Role(RoleBase, ORMModel):
	"""Role schema."""

	id: str
