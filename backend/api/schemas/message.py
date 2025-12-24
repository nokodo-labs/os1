"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import Field, field_validator

from api.models.message import MessageType
from api.schemas.common import MetadataModel
from api.schemas.content import (
	ContentPart,
)
from nokodo_ai.utils.typeid import TypeID


# Type adapter for content validation
ContentPartList = Annotated[list[ContentPart], Field(default_factory=list)]


class MessageBase(MetadataModel):
	"""Shared message attributes."""

	type: MessageType = MessageType.USER
	content: ContentPartList = Field(default_factory=list)
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	usage: dict[str, Any] | None = None
	read_by: list[TypeID] = Field(default_factory=list)


class MessageCreate(MetadataModel):
	"""Payload for creating a message within a thread.

	Content can be provided as:
	- A string (converted to [TextContent(text=...)])
	- A list of content part dicts or ContentPart objects
	"""

	type: MessageType = MessageType.USER
	content: str | list[dict[str, Any] | ContentPart] = ""
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	usage: dict[str, Any] | None = None
	read_by: list[TypeID] = Field(default_factory=list)
	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None

	@field_validator("content", mode="before")
	@classmethod
	def normalize_content(
		cls,
		v: str | list[dict[str, Any] | ContentPart],
	) -> list[dict[str, Any]]:
		"""Normalize content to list of content part dicts."""
		if isinstance(v, str):
			return [{"type": "text", "text": v}] if v else []
		result = []
		for item in v:
			if isinstance(item, dict):
				result.append(item)
			else:
				# It's a ContentPart model
				result.append(item.model_dump())
		return result


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
