"""Thread schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.models.thread import ThreadType
from api.schemas.common import MetadataModel, ORMModel
from api.schemas.message import Message
from api.schemas.user import User


class ThreadBase(MetadataModel):
	"""Fields shared across thread payloads."""

	title: str | None = None
	folder: str | None = None
	tags: list[str] = Field(default_factory=list)
	is_archived: bool = False
	project_id: str | None = None
	group_id: str | None = None
	thread_type: ThreadType = ThreadType.AI_ASSISTANT


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
	thread_type: ThreadType = ThreadType.AI_ASSISTANT


class Thread(ThreadBase, ORMModel):
	"""Detailed response schema."""

	id: str
	user_id: int
	last_activity_at: datetime
	created_at: datetime
	updated_at: datetime
	user_participants: list[User] = Field(default_factory=list)
	# agent_participants: list[Agent] = Field(default_factory=list)
	owner: User | None = None
	messages: list[Message] = Field(default_factory=list)


Thread.model_rebuild()
