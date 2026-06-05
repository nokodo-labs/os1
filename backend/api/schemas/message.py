"""message schemas."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	TypeAdapter,
	field_serializer,
	field_validator,
	model_validator,
)

from api.models.message import MessageType
from api.schemas.common import (
	MetadataModel,
	MetadataUpdateModel,
	ORMModel,
	TimestampedModel,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import BaseContentPart as SDKContentPart
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


class CitationSource(StrEnum):
	"""what kind of resource a citation points to."""

	URL = "url"
	FILE = "file"
	NOTE = "note"
	THREAD = "thread"
	PROJECT = "project"
	REMINDER = "reminder"
	REMINDER_LIST = "reminder_list"
	CALENDAR = "calendar"
	CALENDAR_EVENT = "calendar_event"


class Citation(ORMModel):
	"""a single citation reference within a message.

	citations are reference-based: markers like [n] live in the message text,
	and full citation data lives in message.citations[]. ``index`` is the
	branch-cumulative number used as the [n] marker. ``source_type``
	discriminates the resource kind. ``source_id`` is the source-specific value
	(URL, TypeID string, etc.).
	"""

	index: Annotated[
		int,
		Field(ge=1, description="branch-cumulative citation number"),
	]
	source_type: CitationSource
	source_id: str = Field(
		description="source-specific value: URL string, TypeID, tool_call_id, etc.",
	)
	title: str | None = None


class BaseContentPart(BaseModel):
	"""base class for all content parts."""

	model_config = ConfigDict(extra="ignore")

	metadata: dict | None = None


class TextContent(BaseContentPart):
	"""plain text content."""

	type: Literal["text"] = "text"
	text: str = ""


class JsonContent(BaseContentPart):
	"""structured json content (for structured outputs)."""

	type: Literal["json"] = "json"
	data: dict | None = None


class FileContent(BaseContentPart):
	"""file content; carries a file_id in metadata or an external url."""

	type: Literal["file"] = "file"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class ImageContent(BaseContentPart):
	"""image content; mirrors FileContent with a distinct type."""

	type: Literal["image"] = "image"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class RefusalContent(BaseContentPart):
	"""refusal content (when the model refuses to respond)."""

	type: Literal["refusal"] = "refusal"
	reason: str = ""


AttachmentRefType = Literal[
	"file",
	"note",
	"thread",
	"project",
	"reminder",
	"reminder_list",
	"calendar_event",
	"calendar",
]


class ResourceAttachment(BaseModel):
	"""reference to an attached resource."""

	model_config = ConfigDict(extra="ignore")

	type: AttachmentRefType
	id: TypeID


ContentPart = Annotated[
	TextContent | JsonContent | ImageContent | FileContent | RefusalContent,
	Field(discriminator="type"),
]

# subset allowed for user messages
UserContentPart = Annotated[
	TextContent | ImageContent | FileContent,
	Field(discriminator="type"),
]

# subset allowed for system messages
SystemContentPart = Annotated[
	TextContent,
	Field(discriminator="type"),
]

ContentPartAdapter: TypeAdapter[ContentPart] = TypeAdapter(ContentPart)


# type adapter for content validation
ContentPartList = Annotated[list[ContentPart], Field(default_factory=list)]


def is_private_metadata_key(key: str) -> bool:
	"""return True for backend-private metadata keys that must not leave the api.

	the single source of truth for message-metadata redaction: any key prefixed
	with ``_`` is private. used by both ``public_message_metadata`` (complete
	messages on REST + the ``message`` SSE event) and the streaming ``delta``
	gate, so every wire path strips identical keys.
	"""
	return key.startswith("_")


def public_message_metadata(metadata: JSONObject | None) -> JSONObject:
	"""return metadata safe to include in API/SSE message payloads."""
	if not metadata:
		return {}
	return {
		key: value
		for key, value in metadata.items()
		if not is_private_metadata_key(key)
	}


class MessageBase(MetadataModel):
	"""shared message attributes."""

	type: MessageType = MessageType.USER
	content: ContentPartList = Field(default_factory=list)
	tool_call_id: str | None = None
	is_error: bool | None = None
	tool_calls: list[dict[str, object]] = Field(default_factory=list)
	read_by: list[TypeID] = Field(default_factory=list)
	citations: list[Citation] = Field(default_factory=list)
	attachments: list[ResourceAttachment] = Field(default_factory=list)


class MessageCreate(MetadataModel):
	"""payload for creating a message within a thread.

	content can be provided as:
	- a string (converted to [TextContent(text=...)])
	- a list of ContentPart objects (validated via discriminated union)
	"""

	type: MessageType = MessageType.USER
	content: str | list[ContentPart] = ""
	tool_call_id: str | None = None
	is_error: bool | None = None
	tool_calls: list[dict[str, object]] = Field(default_factory=list)
	usage: dict[str, object] | None = None
	read_by: list[TypeID] = Field(default_factory=list)
	citations: list[Citation] = Field(default_factory=list)
	attachments: list[ResourceAttachment] = Field(default_factory=list)
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
		v: str | list[object],
	) -> list[ContentPart]:
		"""normalize content to list of ContentPart models.

		accepts strings, dicts (validated via discriminated union), or
		ContentPart instances.
		"""
		if isinstance(v, str):
			return [TextContent(text=v)] if v else []
		return [ContentPartAdapter.validate_python(item) for item in v]

	@classmethod
	def from_sdk_message(
		cls,
		sdk_msg: SDKMessage,
		sender_agent_id: TypeID | None = None,
		sender_user_id: TypeID | None = None,
	) -> MessageCreate:
		"""convert an sdk message to an orm MessageCreate for persistence."""

		def _to_storage_parts(
			parts: Sequence[SDKContentPart],
		) -> list[ContentPart]:
			"""convert content parts for DB storage.

			strips inline data (base64/url) from parts that carry a
			file_id in metadata. file data lives in File storage; only
			the reference is persisted for re-resolution later.
			"""
			result: list[ContentPart] = []
			for p in parts:
				d = p.model_dump()
				if isinstance(d, dict) and (d.get("metadata") or {}).get("file_id"):
					d.pop("base64", None)
					d.pop("url", None)
				result.append(ContentPartAdapter.validate_python(d))
			return result

		match sdk_msg.role:
			case "user":
				assert isinstance(sdk_msg, SDKUserMessage)
				return cls(
					type=MessageType.USER,
					content=_to_storage_parts(sdk_msg.content),
					sender_user_id=sender_user_id,
				)
			case "system":
				assert isinstance(sdk_msg, SDKSystemMessage)
				return cls(
					type=MessageType.SYSTEM,
					content=_to_storage_parts(sdk_msg.content),
				)
			case "assistant":
				assert isinstance(sdk_msg, SDKAssistantMessage)
				return cls(
					type=MessageType.ASSISTANT,
					content=_to_storage_parts(sdk_msg.content),
					tool_calls=[tc.model_dump() for tc in sdk_msg.tool_calls],
					usage=sdk_msg.usage.model_dump() if sdk_msg.usage else None,
					sender_agent_id=sender_agent_id,
				)
			case "tool":
				assert isinstance(sdk_msg, SDKToolMessage)
				parts: list[ContentPart] = [TextContent(text=sdk_msg.tool_output)]
				if sdk_msg.attachments:
					parts.extend(_to_storage_parts(sdk_msg.attachments))
				return cls(
					type=MessageType.TOOL,
					content=parts,
					tool_call_id=sdk_msg.tool_call_id,
					is_error=sdk_msg.is_error,
					metadata_=dict(sdk_msg.metadata or {}),
				)
			case _:
				raise ValueError(f"unknown sdk message role: {sdk_msg.role}")


class MessageUpdate(MetadataUpdateModel):
	"""payload for updating a user message's content in place."""

	content: str | list[ContentPart]

	@field_validator("content", mode="before")
	@classmethod
	def normalize_content(
		cls,
		v: str | list[object],
	) -> list[ContentPart]:
		"""normalize content to list of ContentPart models."""
		if isinstance(v, str):
			return [TextContent(text=v)] if v else []
		return [ContentPartAdapter.validate_python(item) for item in v]


class Message(MessageBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	thread_id: TypeID
	parent_id: TypeID | None = None
	task_id: TypeID | None = None
	sender_agent_id: TypeID | None = None
	sender_user_id: TypeID | None = None

	@field_serializer("metadata")
	def serialize_public_metadata(self, metadata: JSONObject) -> JSONObject:
		"""serialize only metadata that belongs on the public message surface."""
		return public_message_metadata(metadata)
