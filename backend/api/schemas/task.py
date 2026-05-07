"""task schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.event_types import EventType
from api.models.task import TaskStatus, TaskType
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


type TaskSortBy = (
	CommonSortBy
	| Literal[
		"status",
		"task_type",
		"stage",
		"last_event_at",
	]
)
type TaskStateFilter = Literal["active", "ended"]


class TaskListFilters(BaseModel):
	"""filters for listing tasks."""

	user_id: TypeID | None = None
	spawned_thread_id: TypeID | None = None
	status_filter: TaskStatus | None = None
	state_filter: TaskStateFilter | None = None


class TaskBase(MetadataModel):
	"""common task fields."""

	task_type: TaskType = TaskType.CUSTOM
	status: TaskStatus = TaskStatus.RUNNING
	progress: int | None = None
	stage: str | None = None
	result: JSONObject | None = None


class TaskCreate(TaskBase):
	"""payload to start a task."""

	user_id: TypeID
	spawned_thread_id: TypeID | None = None


class TaskUpdate(MetadataUpdateModel):
	"""mutable task fields for PATCH operations."""

	status: TaskStatus | MissingType = MISSING
	progress: int | None | MissingType = MISSING
	stage: str | None | MissingType = MISSING
	result: JSONObject | None | MissingType = MISSING


class Task(TaskBase, TimestampedModel):
	"""response model."""

	id: TypeID
	user_id: TypeID
	spawned_thread_id: TypeID | None = None
	started_at: datetime | None = None
	completed_at: datetime | None = None
	cancelled_at: datetime | None = None
	last_event_at: datetime | None = None


class TaskCancelRequest(BaseModel):
	"""payload to request task cancellation."""

	reason: str | None = Field(default=None, max_length=500)


class TaskEvent(MetadataModel):
	"""task stream/event payload."""

	type: EventType
	task: Task
	data: JSONObject = Field(default_factory=dict)
