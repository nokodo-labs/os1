"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.message import MessageType
from api.schemas.common import MetadataModel


class MessageBase(MetadataModel):
	"""Shared message attributes."""

	type: MessageType = MessageType.USER
	content: str
	attachments: list[dict[str, Any]] = Field(default_factory=list)
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	token_usage: dict[str, Any] | None = None
	read_by: list[int] = Field(default_factory=list)


class MessageCreate(MessageBase):
	"""Payload for creating a message within a thread."""

	task_id: str | None = None
	sender_agent_id: str | None = None
	sender_user_id: int | None = None


class Message(MessageBase):
	"""Response schema."""

	id: str
	thread_id: str
	task_id: str | None = None
	sender_agent_id: str | None = None
	sender_user_id: int | None = None
	created_at: datetime
	updated_at: datetime
