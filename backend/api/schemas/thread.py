"""Thread schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from api.schemas.common import MetadataModel, ORMModel
from api.schemas.message import Message
from api.schemas.project import Project as ProjectSchema
from api.schemas.user import User


def _populate_project_ids(data: Any) -> Any:
	"""Attach project_ids to ORM instances without mutating schema defaults."""
	try:
		from api.models.thread import Thread as ThreadModel  # type: ignore
	except Exception:  # pragma: no cover
		return data

	if isinstance(data, ThreadModel) and not getattr(data, "project_ids", None):
		projects = getattr(data, "__dict__", {}).get("projects")
		if projects:
			project_ids = [
				project.id for project in projects if getattr(project, "id", None)
			]
			setattr(data, "project_ids", project_ids)
	return data


class ThreadBase(MetadataModel):
	"""Fields shared across thread payloads."""

	title: str | None = None
	tags: list[str] = Field(default_factory=list)
	is_archived: bool = False
	project_ids: list[str] = Field(default_factory=list)


class ThreadCreate(ThreadBase):
	"""Payload for creating a thread."""

	owner_id: int


class ThreadUpdate(MetadataModel):
	"""Payload for updating a thread."""

	title: str | None = None
	tags: list[str] | None = None
	is_archived: bool | None = None
	project_ids: list[str] | None = None
	owner_id: int | None = None


class ThreadSummary(ORMModel):
	"""Compact representation for listings."""

	id: str
	title: str | None = None
	last_activity_at: datetime
	project_ids: list[str] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_project_ids(cls, data: Any) -> Any:
		return _populate_project_ids(data)


class Thread(ThreadBase, ORMModel):
	"""Detailed response schema."""

	id: str
	owner_id: int
	last_activity_at: datetime
	created_at: datetime
	updated_at: datetime
	owner: User | None = None
	messages: list[Message] = Field(default_factory=list)
	projects: list[ProjectSchema] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_project_ids(cls, data: Any) -> Any:
		return _populate_project_ids(data)
