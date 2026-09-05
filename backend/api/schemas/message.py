"""message schemas."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	TypeAdapter,
	field_validator,
	model_validator,
)

from api.models.base import TOOL_CALL_ID_LENGTH
from api.models.message import MessageType
from api.permissions import AttachableResourceType, MentionableSubjectType
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	PrivateFacetModel,
	PrivateInputModel,
	PrivateModel,
	TimestampedModel,
)
from nokodo_ai.messages import FinishReason
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.typeid import TypeID


class CitationSource(StrEnum):
	"""what kind of resource a citation points to."""

	URL = "url"
	"""a page on the web."""
	FILE = "file"
	"""a file in the workspace."""
	NOTE = "note"
	"""a note."""
	THREAD = "thread"
	"""another conversation."""
	PROJECT = "project"
	"""a project."""
	REMINDER = "reminder"
	"""a reminder."""
	REMINDER_LIST = "reminder_list"
	"""a reminder list."""
	CALENDAR = "calendar"
	"""a calendar."""
	CALENDAR_EVENT = "calendar_event"
	"""an event on a calendar."""


class Citation(ForbidExtraModel):
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
	"""the ``[n]`` marker this citation is referenced by."""
	source_type: CitationSource
	"""what kind of thing is being cited, which decides how to open it."""
	source_id: str = Field(
		description="source-specific value: URL string, TypeID, tool_call_id, etc.",
	)
	"""identifies the source, in whatever form its type uses."""
	title: str | None = None
	"""human label for the source, when one is known."""


class BaseContentPart(BaseModel):
	"""base class for all content parts."""

	model_config = ConfigDict(extra="forbid")
	"""an unrecognized key is a client bug, and is reported rather than kept."""

	metadata: dict | None = None
	"""data about the part, including the ``file_id`` a stored part carries."""


class TextContent(BaseContentPart):
	"""plain text content."""

	type: Literal["text"] = "text"
	"""discriminator identifying a text part."""
	text: str = ""
	"""the prose itself."""


class JsonContent(BaseContentPart):
	"""structured json content (for structured outputs)."""

	type: Literal["json"] = "json"
	"""discriminator identifying a structured part."""
	data: dict | None = None
	"""the structured answer."""


class FileContent(BaseContentPart):
	"""file content; carries a file_id in metadata or an external url."""

	type: Literal["file"] = "file"
	"""discriminator identifying a file part."""
	url: str | None = None
	"""where the file can be fetched."""
	base64: str | None = None
	"""the bytes inline, stripped before storage when a file_id exists."""
	filename: str | None = None
	"""the file's name."""
	media_type: str | None = None
	"""the file's MIME type."""


class ImageContent(BaseContentPart):
	"""image content; mirrors FileContent with a distinct type."""

	type: Literal["image"] = "image"
	"""discriminator identifying an image part."""
	url: str | None = None
	"""where the image can be fetched."""
	base64: str | None = None
	"""the bytes inline, stripped before storage when a file_id exists."""
	filename: str | None = None
	"""the image's name."""
	media_type: str | None = None
	"""the image's MIME type."""


class RefusalContent(BaseContentPart):
	"""refusal content (when the model refuses to respond)."""

	type: Literal["refusal"] = "refusal"
	"""discriminator identifying a refusal."""
	reason: str = ""
	"""why the model declined."""


class ResourceAttachment(BaseModel):
	"""reference to an attached resource."""

	model_config = ConfigDict(extra="forbid")
	"""an unrecognized key is a client bug, and is reported rather than kept."""

	type: AttachableResourceType
	"""what kind of resource is attached."""
	id: TypeID
	"""which resource, of that kind."""


class MessageMention(BaseModel):
	"""a subject a message addresses.

	addressing only. whether an addressed agent also ACTS is decided by
	invocation, never by the mention itself.
	"""

	model_config = ConfigDict(extra="forbid")
	"""an unrecognized key is a client bug, and is reported rather than kept."""

	type: MentionableSubjectType
	"""what kind of subject is addressed."""
	id: TypeID
	"""which subject, of that kind."""


ContentPart = Annotated[
	TextContent | JsonContent | ImageContent | FileContent | RefusalContent,
	Field(discriminator="type"),
]
"""any part a message's content can hold, discriminated by type."""

UserContentPart = Annotated[
	TextContent | ImageContent | FileContent,
	Field(discriminator="type"),
]
"""what a person can send: prose and attachments, never model-only parts."""

SystemContentPart = Annotated[
	TextContent,
	Field(discriminator="type"),
]
"""a system message is text and nothing else."""

ContentPartAdapter: TypeAdapter[ContentPart] = TypeAdapter(ContentPart)
"""validates a raw content part into its concrete type, by discriminator."""


class ToolCall(ForbidExtraModel):
	"""persisted tool call requested by an assistant message."""

	id: str = Field(max_length=TOOL_CALL_ID_LENGTH)
	"""identifies the call; the tool result references this."""
	name: str = Field(min_length=1, max_length=256)
	"""which tool was called."""
	arguments: JSONValue = Field(default_factory=dict)
	"""the call's arguments."""
	created_at: float | None = None
	"""wall-clock epoch of the call's first streaming delta."""
	updated_at: float | None = None
	"""wall-clock epoch of its latest streaming delta."""
	metadata: JSONObject | None = None
	"""call metadata, including the provider's own id for it."""


class Usage(ForbidExtraModel):
	"""token usage attached to an assistant message."""

	input_tokens: int = Field(default=0, ge=0)
	"""tokens the prompt consumed."""
	output_tokens: int = Field(default=0, ge=0)
	"""tokens the model generated."""
	total_tokens: int = Field(default=0, ge=0)
	"""what the provider billed for."""
	cache_creation_input_tokens: int | None = Field(default=None, ge=0)
	"""prompt tokens written to the provider's cache."""
	cache_read_input_tokens: int | None = Field(default=None, ge=0)
	"""prompt tokens served from that cache."""
	metadata: JSONObject | None = None
	"""provider-specific usage detail."""


ContentPartList = Annotated[list[ContentPart], Field(default_factory=list)]
"""a message's content, defaulting to empty rather than absent."""


class MessageBase(MetadataModel):
	"""attributes returned for a persisted message."""

	type: MessageType = MessageType.USER
	"""which kind of message this is."""
	content: ContentPartList = Field(default_factory=list)
	"""the message body."""
	tool_call_id: str | None = Field(default=None, max_length=TOOL_CALL_ID_LENGTH)
	"""the tool call this answers, on a tool message."""
	is_error: bool | None = None
	"""whether a tool result reports a failure."""
	tool_calls: list[ToolCall] = Field(default_factory=list)
	"""tool calls an assistant message requested."""
	finish_reason: FinishReason | None = None
	"""why generation stopped, on an assistant message."""
	citations: list[Citation] = Field(default_factory=list)
	"""sources this message cites."""
	attachments: list[ResourceAttachment] = Field(default_factory=list)
	"""resources this message shares into the thread."""
	mentions: list[MessageMention] = Field(default_factory=list)
	"""subjects this message addresses."""


class MessagePrivate(PrivateModel):
	"""operator-only view of a message: its private metadata.

	carries the backend-owned keys (provider payloads, citation state, sandbox
	ids). no private columns yet, so the inherited ``metadata`` is the whole
	facet; it is still a named type so the generated client schema does not
	have to be renamed when a private column is added.
	"""


class MessagePrivateInput(PrivateInputModel):
	"""operator-only fields on a message write (see ``MessagePrivate``)."""


class MessageRange(ForbidExtraModel):
	"""contiguous message range replaced by a splice."""

	head_id: TypeID
	"""first message of the range being replaced."""
	tail_id: TypeID
	"""last message of it."""


class RunBlockRef(ForbidExtraModel):
	"""run block replaced by a splice."""

	run_id: TypeID
	"""the run whose output is being replaced."""
	run_head_message_id: TypeID
	"""that run's first visible message, which identifies the block."""


type ReplacementTarget = MessageRange | RunBlockRef
"""what a splice replaces: an explicit range, or one run's whole output."""


class ThreadLeaf(ForbidExtraModel):
	"""the canon thread branch becomes current at the spliced message."""

	kind: Literal["thread"]
	"""discriminator identifying the canon conversation."""


class BranchLeaf(ForbidExtraModel):
	"""an off-canon branch becomes current at the spliced message."""

	kind: Literal["branch"]
	"""discriminator identifying a sub-thread."""
	root_id: TypeID
	"""the message that roots the branch."""


type LeafTarget = Annotated[
	ThreadLeaf | BranchLeaf,
	Field(discriminator="kind"),
]
"""which conversation a write makes current, discriminated by kind."""


class MessageSplice(ForbidExtraModel):
	"""structural effect of inserting one message into a thread tree."""

	parent_id: TypeID | None
	"""what the message chains onto; None starts a conversation."""
	reparent_message_ids: list[TypeID] = Field(default_factory=list)
	"""messages moved to chain onto this one instead of its parent."""
	replaces: ReplacementTarget | None = None
	"""output this message supersedes, when it is a regeneration."""
	leaf: LeafTarget | None = None
	"""the conversation this write makes current; None advances nothing."""


class MessageCreate(MetadataModel, ForbidExtraModel):
	"""payload for creating a message within a thread. HTTP-only.

	the wire never carries the private facet: backend-owned metadata reaches
	the column through a ``MessageDraft``, which this type cannot express and
	``extra="forbid"`` refuses to accept.

	content accepts a string (converted to one text part) or a list of
	ContentPart objects; either way it normalizes to a list.
	"""

	type: MessageType = MessageType.USER
	"""which kind of message to create."""
	content: list[ContentPart] = Field(default_factory=list, max_length=256)
	"""the message body."""
	tool_call_id: str | None = Field(default=None, max_length=TOOL_CALL_ID_LENGTH)
	"""the tool call this answers, on a tool message."""
	is_error: bool | None = None
	"""whether a tool result reports a failure."""
	tool_calls: list[ToolCall] = Field(default_factory=list, max_length=128)
	"""tool calls an assistant message requests."""
	usage: Usage | None = None
	"""provider token counts, for a message replayed from elsewhere."""
	citations: list[Citation] = Field(default_factory=list)
	"""sources this message cites."""
	attachments: list[ResourceAttachment] = Field(default_factory=list)
	"""resources to share into the thread, which requires admin on each."""
	originated_resources: list[ResourceAttachment] = Field(default_factory=list)
	"""resources this message created, recorded as originating here."""
	splice: MessageSplice | None = None
	"""explicit placement; omitted lets the server derive it."""
	reply_to_message_id: TypeID | None = None
	"""what this message answers - semantic, and separate from placement."""
	mentions: list[MessageMention] = Field(default_factory=list)
	"""subjects to address, which is what can invoke an agent."""
	task_id: TypeID | None = None
	"""the task this message belongs to."""
	sender_user_id: TypeID | None = None
	"""author, when writing on another user's behalf; operators only."""

	@field_validator("metadata")
	@classmethod
	def reject_run_metadata(cls, value: JSONObject) -> JSONObject:
		"""reject metadata keys owned by run and steering state."""
		reserved = {
			"run_id",
			"agent_id",
			"steering_state",
			"steering_enqueued_at",
			"steering_injected_at",
			"steering_dropped_at",
		}
		if reserved.intersection(value):
			raise ValueError("metadata contains server-owned run fields")
		return value

	@model_validator(mode="after")
	def validate_message_type_fields(self) -> MessageCreate:
		"""validate fields based on message type.

		ensures type-specific fields are present/absent as appropriate:
		- tool: requires tool_call_id, is_error; forbids tool_calls, usage
		- assistant: allows tool_calls and usage; forbids tool fields
		- user/system: forbids assistant and tool fields
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
		if self.type == MessageType.USER and any(
			not isinstance(part, TextContent | ImageContent | FileContent)
			for part in self.content
		):
			raise ValueError("user messages support text, image, and file content")
		if self.type == MessageType.SYSTEM and any(
			not isinstance(part, TextContent) for part in self.content
		):
			raise ValueError("system messages support text content")
		return self

	@field_validator("mentions")
	@classmethod
	def reject_duplicate_mentions(cls, v: list[MessageMention]) -> list[MessageMention]:
		"""a message addresses each subject at most once."""
		seen = {(mention.type, str(mention.id)) for mention in v}
		if len(seen) != len(v):
			raise ValueError("mentions must not repeat a subject")
		return v

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


class MessageUpdate(MetadataUpdateModel, ForbidExtraModel):
	"""payload for updating a user message's content in place.

	no ``private`` facet, and none needed: no producer, internal or wire,
	patches private metadata through a message update (see ``MessageCreate``
	for why the wire type must not carry the facet).
	"""

	content: str | list[ContentPart] | MissingType = MISSING
	"""the replacement body; MISSING leaves it untouched."""
	attachments: list[ResourceAttachment] | MissingType = MISSING
	"""the replacement attachment set; MISSING leaves it untouched."""

	@field_validator("content", mode="before")
	@classmethod
	def normalize_content(
		cls,
		v: str | list[object] | MissingType,
	) -> list[ContentPart] | MissingType:
		"""normalize content to list of ContentPart models."""
		if isinstance(v, str):
			return [TextContent(text=v)] if v else []
		if isinstance(v, list):
			return [ContentPartAdapter.validate_python(item) for item in v]
		return MISSING


class Message(MessageBase, TimestampedModel, PrivateFacetModel[MessagePrivate]):
	"""response schema."""

	id: TypeID
	"""identifies the message."""
	thread_id: TypeID
	"""the conversation it belongs to."""
	parent_id: TypeID | None = None
	"""structural position: what it is chained onto."""
	reply_to_message_id: TypeID | None = None
	"""what it semantically answers, which need not be its parent."""
	branch_current_message_id: TypeID | None = None
	"""current message of the sub-thread rooted here, when one exists."""
	task_id: TypeID | None = None
	"""the task that produced it."""
	sender_agent_id: TypeID | None = None
	"""the agent that authored it."""
	sender_user_id: TypeID | None = None
	"""the person that authored it."""


class MessageCreatedFrame(Message):
	"""message-created SSE payload with its applied structural splice."""

	splice: MessageSplice
	"""where the message landed, which only the writer knows."""
