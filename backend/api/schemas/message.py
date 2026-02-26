"""Message schemas."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator

from api.models.message import MessageType
from api.schemas.common import MetadataModel, TimestampedModel
from api.schemas.content import (
	ContentPart,
	TextContent,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


# Type adapter for content validation
ContentPartList = Annotated[list[ContentPart], Field(default_factory=list)]


class MessageBase(MetadataModel):
	"""Shared message attributes."""

	type: MessageType = MessageType.USER
	content: ContentPartList = Field(default_factory=list)
	tool_call_id: str | None = None
	is_error: bool | None = None
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
	tool_call_id: str | None = None
	is_error: bool | None = None
	tool_calls: list[dict[str, Any]] = Field(default_factory=list)
	usage: dict[str, Any] | None = None
	read_by: list[TypeID] = Field(default_factory=list)
	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None

	@model_validator(mode="after")
	def validate_message_type_fields(self) -> MessageCreate:
		"""validate fields based on message type.

		ensures type-specific fields are present/absent as appropriate:
		- tool: requires tool_call_id, is_error; forbids tool_calls, usage
		- assistant: allows tool_calls, usage; forbids tool_call_id, is_error
		- user/system: forbids tool_call_id, is_error, tool_calls, usage
		"""
		match self.type:
			case MessageType.TOOL:
				if not self.tool_call_id:
					raise ValueError("tool_call_id is required for tool messages")
				if self.is_error is None:
					raise ValueError("is_error is required for tool messages")
				if self.tool_calls:
					raise ValueError("tool_calls is not valid for tool messages")
				if self.usage is not None:
					raise ValueError("usage is not valid for tool messages")
			case MessageType.ASSISTANT:
				if self.tool_call_id is not None:
					raise ValueError("tool_call_id is only valid for tool messages")
				if self.is_error is not None:
					raise ValueError("is_error is only valid for tool messages")
			case MessageType.USER | MessageType.SYSTEM:
				if self.tool_call_id is not None:
					raise ValueError("tool_call_id is only valid for tool messages")
				if self.is_error is not None:
					raise ValueError("is_error is only valid for tool messages")
				if self.tool_calls:
					raise ValueError("tool_calls is only valid for assistant messages")
				if self.usage is not None:
					raise ValueError("usage is only valid for assistant messages")
		return self

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

	@classmethod
	def from_sdk_message(
		cls,
		sdk_msg: SDKMessage,
		*,
		sender_agent_id: TypeID | None = None,
		sender_user_id: TypeID | None = None,
	) -> MessageCreate:
		"""convert an sdk message to an orm MessageCreate for persistence."""
		match sdk_msg.role:
			case "user":
				assert isinstance(sdk_msg, SDKUserMessage)
				return cls(
					type=MessageType.USER,
					content=[part.model_dump() for part in sdk_msg.content],
					sender_user_id=sender_user_id,
				)
			case "system":
				assert isinstance(sdk_msg, SDKSystemMessage)
				return cls(
					type=MessageType.SYSTEM,
					content=[part.model_dump() for part in sdk_msg.content],
				)
			case "assistant":
				assert isinstance(sdk_msg, SDKAssistantMessage)
				return cls(
					type=MessageType.ASSISTANT,
					content=[part.model_dump() for part in sdk_msg.content],
					tool_calls=[tc.model_dump() for tc in sdk_msg.tool_calls],
					usage=sdk_msg.usage.model_dump() if sdk_msg.usage else None,
					sender_agent_id=sender_agent_id,
				)
			case "tool":
				assert isinstance(sdk_msg, SDKToolMessage)
				return cls(
					type=MessageType.TOOL,
					content=[TextContent(text=sdk_msg.tool_output).model_dump()],
					tool_call_id=sdk_msg.tool_call_id,
					is_error=sdk_msg.is_error,
					metadata_=dict(sdk_msg.metadata or {}),
				)
			case _:
				raise ValueError(f"unknown sdk message role: {sdk_msg.role}")


class MessageUpdate(MetadataModel):
	"""Payload for updating a user message's content in place."""

	content: str | list[dict[str, Any] | ContentPart]

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
				result.append(item.model_dump())
		return result


class Message(MessageBase, TimestampedModel):
	"""Response schema."""

	id: TypeID
	thread_id: TypeID
	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None
