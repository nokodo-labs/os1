"""thread schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from api.schemas.common import (
	MetadataModel,
	MetadataUpdateModel,
	ORMModel,
	TimestampedModel,
)
from api.schemas.project import Project as ProjectSchema
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type ThreadSortBy = (
	CommonSortBy
	| Literal[
		"last_activity_at",
		"title",
	]
)


def _populate_project_ids(data: Any) -> Any:
	"""attach project_ids to ORM instances without mutating schema defaults."""
	try:
		from api.models.thread import Thread as ThreadModel
	except Exception:  # pragma: no cover
		return data

	if isinstance(data, ThreadModel) and getattr(data, "is_temporary", None) is None:
		data.is_temporary = False

	if isinstance(data, ThreadModel) and getattr(data, "is_archived", None) is None:
		data.is_archived = False

	if isinstance(data, ThreadModel) and not getattr(data, "project_ids", None):
		projects = getattr(data, "__dict__", {}).get("projects")
		if projects:
			project_ids = [
				project.id for project in projects if getattr(project, "id", None)
			]
			setattr(data, "project_ids", project_ids)
	return data


class ThreadBase(MetadataModel):
	"""fields shared across thread payloads."""

	title: str | None = None
	tags: list[str] = Field(default_factory=list)
	is_archived: bool = False
	is_temporary: bool = False
	project_ids: list[TypeID] = Field(default_factory=list)


class ThreadCreate(ThreadBase):
	"""payload for creating a thread."""

	owner_id: TypeID


class ThreadUpdate(MetadataUpdateModel):
	"""payload for updating a thread."""

	title: str | None = None
	tags: list[str] | None = None
	is_archived: bool | None = None
	is_temporary: bool | None = None
	project_ids: list[TypeID] | None = None
	owner_id: TypeID | None = None
	current_message_id: TypeID | None = None


class ThreadSummary(ORMModel):
	"""compact representation for listings."""

	id: TypeID
	title: str | None = None
	is_temporary: bool = False
	last_activity_at: datetime
	project_ids: list[TypeID] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_project_ids(cls, data: Any) -> Any:
		return _populate_project_ids(data)


class Thread(ThreadBase, TimestampedModel):
	"""detailed response schema."""

	id: TypeID
	owner_id: TypeID
	current_message_id: TypeID | None = None
	last_activity_at: datetime
	deleted_at: datetime | None = None
	projects: list[ProjectSchema] = Field(default_factory=list)

	@model_validator(mode="before")
	@classmethod
	def _ensure_project_ids(cls, data: Any) -> Any:
		return _populate_project_ids(data)


class ThreadSwitchRequest(ORMModel):
	"""payload to switch a thread's active branch."""

	message_id: TypeID


class ThreadSwitchResponse(ORMModel):
	"""response for a thread branch switch."""

	ok: bool
	current_message_id: TypeID | None = None


class ThreadMetadataGenerateRequest(ORMModel):
	"""request body for generating thread metadata."""

	replace: bool = False
	model_id: TypeID | None = None
