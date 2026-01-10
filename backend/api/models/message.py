"""Message model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import ContentPart as SDKContentPart
from nokodo_ai.messages import ContentPartAdapter as SDKContentPartAdapter
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemContentPart as SDKSystemContentPart
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import ToolCall as SDKToolCall
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.messages import Usage as SDKUsage
from nokodo_ai.messages import UserContentPart as SDKUserContentPart
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.utils.typeid import TypeID


_user_content_adapter = TypeAdapter(SDKUserContentPart)
_system_content_adapter = TypeAdapter(SDKSystemContentPart)


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.event import Event
	from api.models.file import File
	from api.models.task import Task
	from api.models.thread import Thread
	from api.models.user import User


class MessageType(StrEnum):
	"""Available message types."""

	USER = "user"
	ASSISTANT = "assistant"
	TOOL = "tool"
	SYSTEM = "system"


class Message(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Stores timeline entries for a thread."""

	__tablename__ = "messages"
	__typeid_prefix__ = "msg"

	thread_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	parent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	task_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("tasks.id", ondelete="SET NULL"),
		index=True,
	)
	sender_agent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="SET NULL"),
		index=True,
	)
	sender_user_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="SET NULL"),
		index=True,
	)
	type: Mapped[MessageType] = mapped_column(
		StringEnum(MessageType),
		default=MessageType.USER,
	)
	# Ordered list of content parts (TextContent, ImageContent, etc.)
	# Each part is a dict with "type" discriminator matching api.schemas.content
	content: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	# Tool-specific fields. Nullable for non-tool messages.
	tool_call_id: Mapped[str | None] = mapped_column(String(TYPEID_LENGTH), index=True)
	is_error: Mapped[bool | None] = mapped_column(Boolean)
	tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	# Token usage from LLM response (matches SDK Usage model)
	usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	read_by: Mapped[list[str]] = mapped_column(JSON, default=list)

	__mapper_args__ = {
		"polymorphic_on": type,
		"polymorphic_identity": "message",
	}

	thread: Mapped[Thread] = relationship(
		"Thread",
		back_populates="messages",
		innerjoin=True,
		foreign_keys=[thread_id],
	)
	parent: Mapped[Message | None] = relationship(
		"Message",
		remote_side="Message.id",
		foreign_keys=[parent_id],
		back_populates="children",
	)
	children: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="parent",
		passive_deletes=True,
		foreign_keys="Message.parent_id",
	)
	task: Mapped[Task | None] = relationship(
		"Task",
		back_populates="messages",
		foreign_keys=[task_id],
		primaryjoin="Message.task_id == Task.id",
	)
	sender_agent: Mapped[Agent | None] = relationship(
		"Agent",
		back_populates="messages",
		foreign_keys=[sender_agent_id],
	)
	sender_user: Mapped[User | None] = relationship(
		"User",
		foreign_keys=[sender_user_id],
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="message",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	files: Mapped[list[File]] = relationship(
		"File",
		back_populates="message",
	)

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
		"""convert this orm message to an sdk message.

		prefer calling the polymorphic subclass implementation (UserMessage, etc.)
		to get a properly typed sdk return.
		"""
		match self.type:
			case MessageType.USER:
				return SDKUserMessage(
					content=self._sdk_user_content(),
					metadata=self.metadata_,
				)
			case MessageType.SYSTEM:
				return SDKSystemMessage(
					content=self._sdk_system_content(),
					metadata=self.metadata_,
				)
			case MessageType.ASSISTANT:
				tool_calls = [
					SDKToolCall.model_validate(tc) for tc in (self.tool_calls or [])
				]
				usage = SDKUsage.model_validate(self.usage) if self.usage else None
				return SDKAssistantMessage(
					content=self._sdk_content(),
					tool_calls=tool_calls,
					usage=usage,
					metadata=self.metadata_,
				)
			case MessageType.TOOL:
				output = ""
				if self.content:
					part = SDKTextContent.model_validate(self.content[0])
					output = part.text
				return SDKToolMessage(
					tool_call_id=self.tool_call_id or "",
					tool_output=output,
					is_error=self.is_error or False,
					metadata=self.metadata_,
				)
			case _:
				return SDKUserMessage(
					content=self._sdk_user_content(),
					metadata=self.metadata_,
				)


class UserMessage(Message):
	"""User message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.USER}

	def to_sdk(self) -> SDKUserMessage:
		return SDKUserMessage(
			content=self._sdk_user_content(),
			metadata=self.metadata_,
		)


class AssistantMessage(Message):
	"""Assistant message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.ASSISTANT}

	def to_sdk(self) -> SDKAssistantMessage:
		tool_calls = [SDKToolCall.model_validate(tc) for tc in (self.tool_calls or [])]
		usage = SDKUsage.model_validate(self.usage) if self.usage else None
		return SDKAssistantMessage(
			content=self._sdk_content(),
			tool_calls=tool_calls,
			usage=usage,
			metadata=self.metadata_,
		)


class ToolMessage(Message):
	"""Tool message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.TOOL}

	def to_sdk(self) -> SDKToolMessage:
		output = ""
		if self.content:
			part = SDKTextContent.model_validate(self.content[0])
			output = part.text
		return SDKToolMessage(
			tool_call_id=self.tool_call_id or "",
			tool_output=output,
			is_error=self.is_error or False,
			metadata=self.metadata_,
		)


class SystemMessage(Message):
	"""System message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.SYSTEM}

	def to_sdk(self) -> SDKSystemMessage:
		return SDKSystemMessage(
			content=self._sdk_system_content(),
			metadata=self.metadata_,
		)
