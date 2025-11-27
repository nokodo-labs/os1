"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.message import MessageRole
from api.schemas.common import MetadataModel


class MessageBase(MetadataModel):
	"""Shared message attributes."""

	role: MessageRole = MessageRole.USER
	content: str
	attachments: list[dict[str, Any]] = Field(default_factory=list)
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	token_usage: dict[str, Any] | None = None


class MessageCreate(MessageBase):
	"""Payload for creating a message within a thread."""

	task_id: str | None = None
	agent_id: str | None = None


class Message(MessageBase):
	"""Response schema."""

	id: str
	thread_id: str
	task_id: str | None = None
	agent_id: str | None = None
	created_at: datetime
	updated_at: datetime
