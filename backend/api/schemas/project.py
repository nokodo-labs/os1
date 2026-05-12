"""Project schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

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


type ProjectSortBy = CommonSortBy | Literal["name"]


class ProjectBase(MetadataModel):
	"""Base project schema."""

	name: str
	description: str | None = None


class ProjectCreate(ProjectBase):
	"""Schema for creating a project."""

	pass


class ProjectUpdate(MetadataUpdateModel):
	"""Schema for updating a project."""

	name: str | MissingType = MISSING
	description: str | None | MissingType = MISSING


class Project(ProjectBase, TimestampedModel, ORMModel):
	"""Project schema."""

	id: TypeID
	owner_id: TypeID
	thread_ids: list[TypeID] = Field(default_factory=list)


class ProjectResourceCounts(ORMModel):
	"""resource counts for one project."""

	thread_count: int = 0
	note_count: int = 0
	file_count: int = 0
	reminder_list_count: int = 0
	calendar_count: int = 0
	resource_count: int = 0
