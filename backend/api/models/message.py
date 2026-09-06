"""message model."""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Boolean, ForeignKey, Index, String, Text, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TOOL_CALL_ID_LENGTH, TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import ContentPart as SDKContentPart
from nokodo_ai.messages import ContentPartAdapter as SDKContentPartAdapter
from nokodo_ai.messages import FileContent as SDKFileContent
from nokodo_ai.messages import FinishReason as SDKFinishReason
from nokodo_ai.messages import ImageContent as SDKImageContent
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemContentPart as SDKSystemContentPart
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import ToolAttachment as SDKToolAttachment
from nokodo_ai.messages import ToolCall as SDKToolCall
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import Usage as SDKUsage
from nokodo_ai.messages import UserContentPart as SDKUserContentPart
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


_user_content_adapter: TypeAdapter[SDKUserContentPart] = TypeAdapter(SDKUserContentPart)
"""validates stored parts into the narrower set a user message may hold."""
_system_content_adapter: TypeAdapter[SDKSystemContentPart] = TypeAdapter(
	SDKSystemContentPart
)
"""validates stored parts into the text-only set a system message may hold."""


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.event import Event
	from api.models.message_attachment import MessageAttachment
	from api.models.message_mention import MessageMention
	from api.models.task import Task
	from api.models.thread import Thread
	from api.models.user import User


class MessageType(StrEnum):
	"""available message types."""

	USER = "user"
	"""authored by a person."""
	ASSISTANT = "assistant"
	"""produced by a model."""
	TOOL = "tool"
	"""the result of one tool call."""
	SYSTEM = "system"
	"""instructions or a system-authored notice."""


class Message(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""stores timeline entries for a thread."""

	__tablename__ = "messages"
	__typeid_prefix__ = "msg"
	__table_args__ = (
		Index(
			"idx_messages_search_text_trgm",
			"search_text",
			postgresql_using="gin",
			postgresql_ops={"search_text": "gin_trgm_ops"},
			postgresql_where=text("search_text IS NOT NULL"),
		),
	)

	thread_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	"""the conversation this message belongs to."""
	parent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	"""structural position: what this message is chained onto."""
	reply_to_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
		index=True,
	)
	"""message this one semantically answers."""
	branch_current_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
		index=True,
	)
	"""current message of the off-canon branch rooted by this message."""
	task_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("tasks.id", ondelete="SET NULL"),
		index=True,
	)
	"""the task that produced this message, when one did."""
	sender_agent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="SET NULL"),
		index=True,
	)
	"""the agent that authored this message."""
	sender_user_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="SET NULL"),
		index=True,
	)
	"""the person that authored this message."""
	type: Mapped[MessageType] = mapped_column(
		StringEnum(MessageType),
		default=MessageType.USER,
	)
	"""which kind of message this is, and which subclass maps it."""
	content: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
	"""ordered content parts, as stored (see ``api.schemas.message``)."""
	tool_call_id: Mapped[str | None] = mapped_column(
		String(TOOL_CALL_ID_LENGTH), index=True
	)
	"""the tool call this message answers; set only on tool messages."""
	is_error: Mapped[bool | None] = mapped_column(Boolean)
	"""whether a tool result reports a failure."""
	tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
	"""tool calls an assistant message requested."""
	finish_reason: Mapped[SDKFinishReason | None] = mapped_column(String(50))
	"""why generation stopped, for an assistant message."""
	usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
	"""provider token counts, matching the SDK's ``Usage`` shape."""
	citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
	"""sources this message cites (see ``api.schemas.message``)."""
	search_text: Mapped[str | None] = mapped_column(Text)
	"""text parts joined for trigram search, maintained by a mapper event.

	user and assistant messages only: tool output is mechanism, and matching
	it would surface rows nobody wrote.
	"""

	__mapper_args__ = {
		"polymorphic_on": type,
		"polymorphic_abstract": True,
	}

	thread: Mapped[Thread] = relationship(
		"Thread",
		back_populates="messages",
		innerjoin=True,
		foreign_keys=[thread_id],
	)
	"""the conversation this message belongs to."""
	parent: Mapped[Message | None] = relationship(
		"Message",
		remote_side="Message.id",
		foreign_keys=[parent_id],
		back_populates="children",
	)
	"""the message this one is chained onto."""
	children: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="parent",
		passive_deletes=True,
		foreign_keys="Message.parent_id",
	)
	"""messages chained onto this one; more than one means it branches."""
	task: Mapped[Task | None] = relationship(
		"Task",
		back_populates="messages",
		foreign_keys=[task_id],
		primaryjoin="Message.task_id == Task.id",
	)
	"""the task that produced this message."""
	sender_agent: Mapped[Agent | None] = relationship(
		"Agent",
		back_populates="messages",
		foreign_keys=[sender_agent_id],
	)
	"""the agent that authored this message."""
	sender_user: Mapped[User | None] = relationship(
		"User",
		foreign_keys=[sender_user_id],
	)
	"""the person that authored this message."""
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="message",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	"""events anchored to this message, which is how participants read them."""
	attachment_links: Mapped[list[MessageAttachment]] = relationship(
		"MessageAttachment",
		back_populates="message",
		cascade="all, delete-orphan",
		passive_deletes=True,
		order_by="MessageAttachment.position",
	)
	"""resources this message shares into the thread, in order."""
	mention_links: Mapped[list[MessageMention]] = relationship(
		"MessageMention",
		back_populates="message",
		cascade="all, delete-orphan",
		passive_deletes=True,
		order_by="MessageMention.position",
	)
	"""subjects this message addresses, in order."""

	@property
	def attachments(self) -> list[dict[str, object]]:
		"""ordered resources attached to this message."""
		return [attachment.resource_ref for attachment in self.attachment_links]

	@property
	def mentions(self) -> list[dict[str, object]]:
		"""ordered subjects this message addresses."""
		return [mention.subject_ref for mention in self.mention_links]

	@property
	def mentioned_agent_ids(self) -> list[TypeID]:
		"""agents this message addresses."""
		return [
			TypeID(str(mention.agent_id))
			for mention in self.mention_links
			if mention.agent_id is not None
		]

	@property
	def text_content(self) -> str:
		"""extract concatenated text from all text content parts."""
		parts: list[str] = []
		for part in self.content or []:
			if isinstance(part, dict) and part.get("type") == "text":
				text = str(part.get("text", "")).strip()
				if text:
					parts.append(text)
		return " ".join(parts)

	def _sdk_metadata(self) -> JSONObject:
		"""this message's metadata in the SDK's flat, prefixed shape."""
		return {
			**{
				key: value
				for key, value in self.public_metadata.items()
				if not key.startswith("_")
			},
			**{f"_{key}": value for key, value in self.private_metadata.items()},
		}

	def _sdk_content(self) -> list[SDKContentPart]:
		"""validate content parts into sdk models."""
		return [
			SDKContentPartAdapter.validate_python(part) for part in (self.content or [])
		]

	def _sdk_user_content(self) -> list[SDKUserContentPart]:
		"""validate content parts into sdk user content models."""
		return [
			_user_content_adapter.validate_python(part) for part in (self.content or [])
		]

	def _sdk_system_content(self) -> list[SDKSystemContentPart]:
		"""validate content parts into sdk system content models."""
		return [
			_system_content_adapter.validate_python(part)
			for part in (self.content or [])
		]

	def to_sdk(self) -> SDKMessage:
		"""convert a mapped message through its concrete subclass."""
		raise NotImplementedError


def _placeholder_tool_call(raw: object) -> SDKToolCall | None:
	"""rebuild a malformed tool call around whatever id it still carries."""
	if not isinstance(raw, dict):
		return None
	call_id = raw.get("id")
	if not isinstance(call_id, str) or not call_id:
		return None
	return SDKToolCall(id=call_id, name="", arguments={})


class UserMessage(Message):
	"""user message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.USER}

	def to_sdk(self) -> SDKUserMessage:
		"""convert this row into the message the model reads."""
		return SDKUserMessage(
			content=self._sdk_user_content(),
			metadata=self._sdk_metadata(),
		)


class AssistantMessage(Message):
	"""assistant message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.ASSISTANT}

	def to_sdk(self) -> SDKAssistantMessage:
		"""convert this row into the message the model reads.

		historical rows can hold values the current schema rejects, so each is
		repaired or dropped rather than failing the whole conversation load.
		"""
		tool_calls: list[SDKToolCall] = []
		for raw in self.tool_calls or []:
			try:
				tool_calls.append(SDKToolCall.model_validate(raw))
			except ValidationError:
				# a persisted tool result still references this call by id, and
				# every provider rejects a tool result with no matching call.
				# so the id survives as a placeholder even when nothing else
				# about the call does - dropping one side of a pair is the one
				# option that always breaks the next run on this branch.
				placeholder = _placeholder_tool_call(raw)
				if placeholder is not None:
					tool_calls.append(placeholder)
				logger.warning(
					"repairing malformed historical tool call",
					extra={
						"message_id": str(self.id),
						"recovered": placeholder is not None,
					},
				)
		usage = SDKUsage.model_validate(self.usage) if self.usage else None
		return SDKAssistantMessage(
			content=self._sdk_content(),
			tool_calls=tool_calls,
			usage=usage,
			finish_reason=self.finish_reason,
			metadata=self._sdk_metadata(),
		)


class ToolMessage(Message):
	"""tool message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.TOOL}

	def to_sdk(self) -> SDKToolMessage:
		"""convert this row into the tool result the model reads.

		text parts become the output and binary parts become attachments, since
		the SDK carries the two separately.
		"""
		output = ""
		attachments: list[SDKToolAttachment] = []
		for raw in self.content or []:
			part = SDKContentPartAdapter.validate_python(raw)
			if isinstance(part, SDKTextContent):
				output += part.text
			elif isinstance(part, (SDKImageContent, SDKFileContent)):
				attachments.append(part)
		tool_call_id = self.tool_call_id
		if not tool_call_id:
			# same repair as a malformed tool call: a historical row must not
			# break loading the conversation it sits in. the id is synthesized
			# from the row so the result is at least self-consistent; it pairs
			# with no call, and the adapters drop an unpaired result on the way
			# to the provider.
			tool_call_id = f"tool_call_{self.id}"
			logger.warning(
				"repairing historical tool message with no tool_call_id",
				extra={"message_id": str(self.id)},
			)
		return SDKToolMessage(
			tool_call_id=tool_call_id,
			tool_output=output,
			is_error=self.is_error or False,
			metadata=self._sdk_metadata(),
			attachments=attachments,
		)


class SystemMessage(Message):
	"""system message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.SYSTEM}

	def to_sdk(self) -> SDKSystemMessage:
		"""convert this row into the message the model reads."""
		return SDKSystemMessage(
			content=self._sdk_system_content(),
			metadata=self._sdk_metadata(),
		)


@event.listens_for(Message, "before_insert", propagate=True)
@event.listens_for(Message, "before_update", propagate=True)
def _sync_message_search_text(
	_mapper: object, _connection: object, target: Message
) -> None:
	"""keep the searchable text in step with the content on every write.

	derived here rather than at the call sites so no writer can persist a row
	whose search text disagrees with what it actually says.
	"""
	if target.type in (MessageType.USER, MessageType.ASSISTANT):
		target.search_text = target.text_content or None
	else:
		target.search_text = None
