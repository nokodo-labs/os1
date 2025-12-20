"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from api.models.message import MessageType
from api.schemas.common import MetadataModel
from api.typeid import TypeID


class MessageBase(MetadataModel):
	"""Shared message attributes."""

	type: MessageType = MessageType.USER
	content: str
	attachments: list[dict[str, Any]] = Field(default_factory=list)
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	token_usage: dict[str, Any] | None = None
	read_by: list[TypeID] = Field(default_factory=list)


class MessageCreate(MessageBase):
	"""Payload for creating a message within a thread."""

	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None


class Message(MessageBase):
	"""Response schema."""

	id: TypeID
	thread_id: TypeID
	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None
	created_at: datetime
	updated_at: datetime
