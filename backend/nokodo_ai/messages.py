"""message domain models for SDK execution."""

from __future__ import annotations

from abc import ABC
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from nokodo_ai.base import Base
from nokodo_ai.types.json import JSONObject, JSONValue
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


class FileContent(BaseContentPart):
	"""file attachment content part.

	the sdk uses url/base64 for execution. for api/orm persistence,
	store file references in metadata["file_id"].
	"""

	type: Literal["file"] = "file"
	url: str | None = None
	base64: str | None = None
	filename: str | None = None
	media_type: str | None = None


class ImageContent(BaseContentPart):
	"""image content part.

	this mirrors FileContent fields but uses a distinct content type.
	"""

	type: Literal["image"] = "image"
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
	arguments: JSONValue = Field(default_factory=dict)
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


FinishReason = Literal["stop", "length", "tool_calls", "content_filter"]


class AssistantMessage(BaseMessage, _HasTextContentHelpers):
	"""a message from the assistant."""

	role: Literal["assistant"] = "assistant"
	content: list[ContentPart] = Field(
		default_factory=list, description="list of content parts"
	)
	tool_calls: list[ToolCall] = Field(
		default_factory=list,
		description="list of tool calls requested by the assistant",
	)
	usage: Usage | None = Field(default=None, description="token usage information")
	finish_reason: FinishReason | None = Field(
		default=None, description="reason for message completion"
	)

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

	def merge(self, delta: AssistantMessage) -> AssistantMessage:
		"""merge a streamed delta into this message, returning self for chaining.

		handles:
		- text content concatenation
		- tool call argument streaming (matched by id)
		- usage and finish_reason updates
		"""
		# --- merge text content ---
		if delta.text:
			# find existing text part or create one
			text_part = next(
				(p for p in self.content if isinstance(p, TextContent)),
				None,
			)
			if text_part is not None:
				text_part.text += delta.text
			else:
				self.content.append(TextContent(text=delta.text))

		# --- merge other content parts (non-text) ---
		for part in delta.content:
			if isinstance(part, TextContent):
				continue  # already handled above
			# for non-text parts, just append (images, json, refusals, files)
			self.content.append(part)

		# --- merge tool calls ---
		for delta_tc in delta.tool_calls:
			# find existing tool call by id
			existing_tc = next(
				(tc for tc in self.tool_calls if tc.id == delta_tc.id),
				None,
			)
			if existing_tc is not None:
				# append streamed arguments (they come as string chunks)
				if isinstance(existing_tc.arguments, str) and isinstance(
					delta_tc.arguments, str
				):
					existing_tc.arguments += delta_tc.arguments
				elif delta_tc.arguments:
					# if delta has parsed dict or first chunk, just assign
					existing_tc.arguments = delta_tc.arguments
				# update name if provided (usually comes in first chunk)
				if delta_tc.name:
					existing_tc.name = delta_tc.name
			else:
				# new tool call, append it
				self.tool_calls.append(delta_tc.model_copy(deep=True))

		# --- merge usage (take latest non-None) ---
		if delta.usage is not None:
			if self.usage is None:
				self.usage = delta.usage
			else:
				# accumulate tokens
				self.usage.input_tokens += delta.usage.input_tokens
				self.usage.output_tokens += delta.usage.output_tokens
				self.usage.total_tokens += delta.usage.total_tokens

		# --- merge finish_reason (take latest non-None) ---
		if delta.finish_reason is not None:
			self.finish_reason = delta.finish_reason

		# --- merge metadata ---
		if delta.metadata:
			if self.metadata is None:
				self.metadata = delta.metadata
			else:
				self.metadata.update(delta.metadata)

		return self


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
	tool_call_id: str
	tool_output: str
	is_error: bool = False


Message = Annotated[
	UserMessage | AssistantMessage | ToolMessage | SystemMessage,
	Field(discriminator="role"),
]

MessageAdapter = TypeAdapter(Message)
