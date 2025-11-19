"""Task schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.models.task import TaskStatus, TaskType
from api.schemas.common import MetadataModel


class TaskBase(MetadataModel):
	"""Common task fields."""

	task_type: TaskType = TaskType.CUSTOM
	status: TaskStatus = TaskStatus.PENDING
	progress: int | None = None
	stage: str | None = None
	result: dict[str, Any] | None = None


class TaskCreate(TaskBase):
	"""Payload to start a task."""

	user_id: int
	spawned_thread_id: str | None = None


class TaskUpdate(MetadataModel):
	"""Mutable task fields for PATCH operations."""

	status: TaskStatus | None = None
	progress: int | None = None
	stage: str | None = None
	result: dict[str, Any] | None = None


class Task(TaskBase):
	"""Response model."""

	id: str
	user_id: int
	spawned_thread_id: str | None = None
	started_at: datetime | None = None
	completed_at: datetime | None = None
	cancelled_at: datetime | None = None
	last_event_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
