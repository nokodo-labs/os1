"""message domain models for SDK execution."""

from __future__ import annotations

from abc import ABC
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from nokodo_ai.base import Base
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils import typeid


# --- content types ---


class BaseContentPart(Base, ABC):
	"""base class for all message content parts."""

	metadata: JSONObject | None = None


class TextContent(BaseContentPart):
	"""text content part."""

	type: Literal["text"] = "text"
	text: str = ""


class JsonContent(BaseContentPart):
	"""structured JSON content part (for structured outputs)."""

	type: Literal["json"] = "json"
	data: JSONObject | None = None


class ImageContent(BaseContentPart):
	"""image content part."""

	type: Literal["image"] = "image"
	url: str | None = None
	base64: str | None = None
	media_type: str | None = None


class FileContent(BaseContentPart):
	"""file attachment content part."""

	type: Literal["file"] = "file"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class RefusalContent(BaseContentPart):
	"""refusal content part (when model refuses to respond)."""

	type: Literal["refusal"] = "refusal"
	reason: str = ""


ContentPart = Annotated[
	TextContent | JsonContent | ImageContent | FileContent | RefusalContent,
	Field(discriminator="type"),
]

ContentPartAdapter = TypeAdapter(ContentPart)


# --- usage tracking ---


class Usage(Base):
	"""token usage information from an LLM response."""

	input_tokens: int = 0
	output_tokens: int = 0
	total_tokens: int = 0
	cache_creation_input_tokens: int | None = None
	cache_read_input_tokens: int | None = None
	metadata: JSONObject | None = None


# --- tool calls and results ---


class ToolCall(Base):
	"""a tool call requested by the assistant."""

	id: str = Field(default_factory=lambda: typeid.new_typeid("tool_call"))
	name: str
	arguments: JSONObject = Field(default_factory=dict)
	metadata: JSONObject | None = None


class ToolResult(Base):
	"""result of a tool call execution."""

	tool_call_id: str
	output: str
	is_error: bool = False
	metadata: JSONObject | None = None


# --- message types ---


class BaseMessage(Base, ABC):
	"""ABC base class for all message types."""

	role: Literal["user", "assistant", "tool", "system"]
	metadata: JSONObject | None = None


class _HasTextContentHelpers(ABC):
	"""shared helpers for messages that support a text constructor."""

	@classmethod
	def from_text(cls, text: str):
		raise NotImplementedError

	@property
	def text(self) -> str:
		raise NotImplementedError


UserContentPart = Annotated[TextContent | ImageContent | FileContent, Field()]


class UserMessage(BaseMessage, _HasTextContentHelpers):
	"""a message from the user.

	user content intentionally cannot include JSON or refusal parts.
	"""

	role: Literal["user"] = "user"
	content: list[UserContentPart] = Field(default_factory=list)

	@classmethod
	def from_text(cls, text: str) -> UserMessage:
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)


class AssistantMessage(BaseMessage, _HasTextContentHelpers):
	"""a message from the assistant."""

	role: Literal["assistant"] = "assistant"
	content: list[ContentPart] = Field(default_factory=list)
	tool_calls: list[ToolCall] = Field(default_factory=list)
	usage: Usage | None = None

	@classmethod
	def from_text(cls, text: str) -> AssistantMessage:
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)

	@property
	def json(self) -> JSONObject | None:
		for part in self.content:
			if isinstance(part, JsonContent):
				return part.data
		return None

	@property
	def refusal(self) -> str | None:
		for part in self.content:
			if isinstance(part, RefusalContent):
				return part.reason
		return None


SystemContentPart = Annotated[TextContent, Field()]


class SystemMessage(BaseMessage):
	"""a system prompt message."""

	role: Literal["system"] = "system"
	content: list[SystemContentPart] = Field(default_factory=list)

	@classmethod
	def from_text(cls, text: str) -> SystemMessage:
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)


class ToolMessage(BaseMessage):
	"""a message containing tool execution results."""

	role: Literal["tool"] = "tool"
	tool_result: ToolResult


Message = Annotated[
	UserMessage | AssistantMessage | ToolMessage | SystemMessage,
	Field(discriminator="role"),
]

MessageAdapter = TypeAdapter(Message)
