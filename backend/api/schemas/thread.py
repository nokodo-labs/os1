"""Thread schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import MetadataModel, ORMModel
from api.schemas.message import Message
from api.schemas.user import User


class ThreadBase(MetadataModel):
	"""Fields shared across thread payloads."""

	title: str | None = None
	folder: str | None = None
	tags: list[str] = Field(default_factory=list)
	is_archived: bool = False


class ThreadCreate(ThreadBase):
	"""Payload for creating a thread."""

	user_id: int


class ThreadUpdate(ThreadBase):
	"""Payload for updating a thread."""

	user_id: int | None = None


class ThreadSummary(ORMModel):
	"""Compact representation for listings."""

	id: str
	title: str | None = None
	last_activity_at: datetime


class Thread(ThreadBase):
	"""Detailed response schema."""

	id: str
	user_id: int
	last_activity_at: datetime
	created_at: datetime
	updated_at: datetime
	owner: User | None = None
	messages: list[Message] = Field(default_factory=list)


Thread.model_rebuild()
