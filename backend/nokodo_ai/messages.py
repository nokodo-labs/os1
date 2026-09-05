"""message domain models for SDK execution."""

from abc import ABC
from time import monotonic, time
from typing import Annotated, Literal, Self

from pydantic import Field, TypeAdapter

from .base import Base
from .types.json import JSONObject, JSONValue
from .utils import typeid


PROVIDER_DATA_KEY = "_provider_data"
"""metadata key holding a provider's own representation of a message part.

kept so a part can be handed back to the provider that produced it without
being lossily rebuilt from our own shape.
"""


# --- content types ---


class BaseContentPart(Base, ABC):
	"""base class for all message content parts."""

	metadata: JSONObject | None = None
	"""data about the part, including its provider-native form and file refs."""


class TextContent(BaseContentPart):
	"""text content part."""

	type: Literal["text"] = "text"
	"""discriminator identifying a text part."""
	text: str = ""
	"""the prose itself."""


class JsonContent(BaseContentPart):
	"""structured JSON content part (for structured outputs)."""

	type: Literal["json"] = "json"
	"""discriminator identifying a structured part."""
	data: JSONObject | None = None
	"""the structured answer, shaped by the requested response model."""


class FileContent(BaseContentPart):
	"""file attachment content part.

	the sdk uses url/base64 for execution. for api/orm persistence,
	store file references in metadata["file_id"].
	"""

	type: Literal["file"] = "file"
	"""discriminator identifying a file part."""
	url: str | None = None
	"""where the provider can fetch the file."""
	base64: str | None = None
	"""the bytes inline, stripped before storage when a file_id exists."""
	filename: str | None = None
	"""the file's name, as shown to the model and the user."""
	media_type: str | None = None
	"""the file's MIME type."""


class ImageContent(BaseContentPart):
	"""image content part.

	this mirrors FileContent fields but uses a distinct content type.
	"""

	type: Literal["image"] = "image"
	"""discriminator identifying an image part."""
	url: str | None = None
	"""where the provider can fetch the image."""
	base64: str | None = None
	"""the bytes inline, stripped before storage when a file_id exists."""
	filename: str | None = None
	"""the image's name."""
	media_type: str | None = None
	"""the image's MIME type."""


class RefusalContent(BaseContentPart):
	"""refusal content part (when model refuses to respond)."""

	type: Literal["refusal"] = "refusal"
	"""discriminator identifying a refusal."""
	reason: str = ""
	"""why the model declined."""


ContentPart = Annotated[
	TextContent | JsonContent | ImageContent | FileContent | RefusalContent,
	Field(discriminator="type"),
]
"""any part a message's content can hold, discriminated by type."""

ContentPartAdapter: TypeAdapter[ContentPart] = TypeAdapter(ContentPart)
"""validates a raw content part into its concrete type, by discriminator."""


# --- usage tracking ---


class Usage(Base):
	"""token usage information from a chat model response."""

	input_tokens: int = 0
	"""tokens the prompt consumed."""
	output_tokens: int = 0
	"""tokens the model generated."""
	total_tokens: int = 0
	"""what the provider billed for, which is not always the sum above."""
	cache_creation_input_tokens: int | None = None
	"""prompt tokens written to the provider's cache, where it has one."""
	cache_read_input_tokens: int | None = None
	"""prompt tokens served from that cache instead of being reprocessed."""
	metadata: JSONObject | None = None
	"""provider-specific usage detail with no cross-provider meaning."""


# --- tool calls and results ---


class ToolCall(Base):
	"""a tool call requested by the assistant."""

	id: str = Field(default_factory=lambda: typeid.new_typeid("tool_call"))
	"""ours, not the provider's: the tool result references this."""
	name: str
	"""which tool the model is asking for."""
	arguments: JSONValue = Field(default_factory=dict)
	"""the call's arguments; a string while they are still streaming in."""
	created_at: float = Field(default_factory=time)
	"""wall-clock epoch of the earliest streaming delta for this tool call."""
	updated_at: float = Field(default_factory=time)
	"""wall-clock epoch of the latest streaming delta for this tool call."""
	created_at_monotonic: float = Field(default_factory=monotonic, exclude=True)
	"""monotonic creation time within one process and stream."""
	metadata: JSONObject | None = None
	"""call metadata, including the provider's own id for this call."""


# --- message types ---


class BaseMessage(Base, ABC):
	"""ABC base class for all message types."""

	role: Literal["user", "assistant", "tool", "system"]
	"""who authored the message; the discriminator every consumer switches on."""
	metadata: JSONObject | None = None
	"""data carried alongside the message, not shown to the model as content."""


class _HasTextContentHelpers(ABC):
	"""shared helpers for messages that support a text constructor."""

	@classmethod
	def from_text(cls, text: str) -> Self:
		"""build a message whose content is one text part."""
		raise NotImplementedError

	@property
	def text(self) -> str:
		"""every text part joined; non-text content is skipped."""
		raise NotImplementedError


UserContentPart = Annotated[TextContent | ImageContent | FileContent, Field()]
"""what a person can send: prose and attachments, never model-only parts."""


class UserMessage(BaseMessage, _HasTextContentHelpers):
	"""a message from the user.

	user content intentionally cannot include JSON or refusal parts.
	"""

	role: Literal["user"] = "user"
	"""identifies this as a user message."""
	content: list[UserContentPart] = Field(default_factory=list)
	"""what the person sent."""

	@classmethod
	def from_text(cls, text: str) -> UserMessage:
		"""build a user message from one string."""
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		"""every text part joined; attachments are skipped."""
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)


FinishReason = Literal["completed", "length", "content_filter"]
"""why the provider stopped generating.

only ever what the provider reported about a response that EXISTS. whether the
model called tools is a property of the content, not a reason, so there is no
``tool_calls`` member. a provider error or a cancellation means no completed
response exists at all: the adapter raises, and the deltas that did arrive form
a partial message whose reason is ``None`` - "the provider never said".
"""


class AssistantMessage(BaseMessage, _HasTextContentHelpers):
	"""a message from the assistant."""

	role: Literal["assistant"] = "assistant"
	"""identifies this as an assistant message."""
	content: list[ContentPart] = Field(
		default_factory=list, description="list of content parts"
	)
	"""what the model produced, which may be empty when it only called tools."""
	tool_calls: list[ToolCall] = Field(
		default_factory=list,
		description="list of tool calls requested by the assistant",
	)
	"""tools the model is asking to run before it can continue."""
	usage: Usage | None = Field(default=None, description="token usage information")
	"""what this turn cost, where the provider reports it."""
	finish_reason: FinishReason | None = Field(
		default=None, description="reason for message completion"
	)
	"""why generation stopped."""
	created_at: float = Field(default_factory=time)
	"""wall-clock epoch of the first delta for this message."""
	updated_at: float = Field(default_factory=time)
	"""wall-clock epoch of the latest delta merged into it."""

	@classmethod
	def from_text(cls, text: str) -> AssistantMessage:
		"""build an assistant message from one string."""
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		"""every text part joined; json and refusal parts are skipped."""
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)

	@property
	def json_content(self) -> JSONObject | None:
		"""the structured payload, when the model answered with one."""
		for part in self.content:
			if isinstance(part, JsonContent):
				return part.data
		return None

	@property
	def refusal(self) -> str | None:
		"""why the model declined, when it did."""
		for part in self.content:
			if isinstance(part, RefusalContent):
				return part.reason
		return None

	def merge(self, delta: AssistantMessage) -> AssistantMessage:
		"""accumulate a streamed delta INTO this message, in place.

		returns self for chaining, so ``x = x.merge(d)`` reads like a value
		update - it is not, and callers holding the same object see the result.

		handles:
		- text content concatenation
		- tool call argument streaming (matched by id)
		- usage and finish_reason updates

		usage is REPLACED, not summed, so a provider that reports per-delta
		increments rather than a running total must accumulate before merging.
		"""
		now = time()
		for part in delta.content:
			if (
				isinstance(part, TextContent)
				and self.content
				and isinstance(self.content[-1], TextContent)
			):
				self.content[-1].text += part.text
			else:
				self.content.append(part.model_copy(deep=True))

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
				# preserve the earliest created_at / created_at_monotonic
				if delta_tc.created_at < existing_tc.created_at:
					existing_tc.created_at = delta_tc.created_at
				if delta_tc.created_at_monotonic < existing_tc.created_at_monotonic:
					existing_tc.created_at_monotonic = delta_tc.created_at_monotonic
				# always bump updated_at to the latest delta
				existing_tc.updated_at = now
			else:
				# new tool call, append it
				self.tool_calls.append(delta_tc.model_copy(deep=True))

		# --- merge usage (take latest non-None) ---
		if delta.usage is not None:
			self.usage = delta.usage.model_copy(deep=True)

		# --- merge finish_reason (take latest non-None) ---
		if delta.finish_reason is not None:
			self.finish_reason = delta.finish_reason

		# --- merge metadata ---
		if delta.metadata:
			if self.metadata is None:
				self.metadata = delta.metadata.copy()
			else:
				self.metadata.update(delta.metadata)

		# --- merge timestamps ---
		# preserve the earliest created_at across deltas
		if delta.created_at < self.created_at:
			self.created_at = delta.created_at
		# always bump updated_at
		self.updated_at = now

		return self


SystemContentPart = Annotated[TextContent, Field()]
"""a system prompt is text and nothing else."""


class SystemMessage(BaseMessage):
	"""a system prompt message."""

	role: Literal["system"] = "system"
	"""identifies this as a system message."""
	content: list[SystemContentPart] = Field(default_factory=list)
	"""the instructions given to the model."""

	@classmethod
	def from_text(cls, text: str) -> SystemMessage:
		"""build a system message from one string."""
		return cls(content=[TextContent(text=text)])

	@property
	def text(self) -> str:
		"""every text part joined."""
		return "".join(
			part.text for part in self.content if isinstance(part, TextContent)
		)


ToolAttachment = Annotated[
	ImageContent | FileContent,
	Field(discriminator="type"),
]
"""what a tool can return besides text."""


class ToolMessage(BaseMessage):
	"""a message containing tool execution results.

	tools can return both text output and optional attachments (images, files).
	attachments are passed to the chat model in subsequent turns and rendered in the UI.
	"""

	role: Literal["tool"] = "tool"
	"""identifies this as a tool result."""
	tool_call_id: str
	"""the call this answers; every provider rejects one that matches none."""
	tool_output: str
	"""what the tool returned, as the model will read it."""
	is_error: bool = False
	"""whether the tool failed, which the model is told rather than hidden."""
	attachments: list[ToolAttachment] = Field(default_factory=list)
	"""files or images the tool produced alongside its output."""


Message = Annotated[
	UserMessage | AssistantMessage | ToolMessage | SystemMessage,
	Field(discriminator="role"),
]
"""any message in a thread, discriminated by role."""

MessageAdapter: TypeAdapter[Message] = TypeAdapter(Message)
"""validates a raw message into its concrete type, by role."""
