"""Project schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type ProjectSortBy = CommonSortBy | Literal["name"]


class ProjectBase(MetadataModel):
	"""Base project schema."""

	name: str
	description: str | None = None


class ProjectCreate(ProjectBase):
	"""Schema for creating a project."""

	pass


class ProjectUpdate(ORMModel):
	"""Schema for updating a project."""

	name: str | None = None
	description: str | None = None


class Project(ProjectBase, TimestampedModel, ORMModel):
	"""Project schema."""

	id: TypeID
	owner_id: TypeID
	thread_ids: list[TypeID] = Field(default_factory=list)
