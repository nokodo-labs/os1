"""Project schemas."""

from __future__ import annotations

from api.schemas.common import MetadataModel, ORMModel, TimestampedModel


class ProjectBase(MetadataModel):
	"""Base project schema."""

	name: str
	description: str | None = None


class ProjectCreate(ProjectBase):
	"""Schema for creating a project."""

	pass


class ProjectUpdate(ProjectBase):
	"""Schema for updating a project."""

	name: str | None = None
	description: str | None = None


class Project(ProjectBase, TimestampedModel, ORMModel):
	"""Project schema."""

	id: str
	owner_id: int
