"""Project schemas."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from api.schemas.typeid import TypeID


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

	id: TypeID
	owner_id: TypeID
	thread_ids: list[TypeID] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_thread_ids(cls, data: Any) -> Any:
		try:
			from api.models.project import Project as ProjectModel  # type: ignore
		except Exception:  # pragma: no cover
			return data

		if isinstance(data, ProjectModel) and not getattr(data, "thread_ids", None):
			threads = getattr(data, "__dict__", {}).get("threads")
			if threads:
				thread_ids = [
					thread.id for thread in threads if getattr(thread, "id", None)
				]
				setattr(data, "thread_ids", thread_ids)
		return data
