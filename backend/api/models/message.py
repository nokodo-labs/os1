"""Message model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import (
	TYPEID_LENGTH,
	MetadataJSONMixin,
	StringEnum,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.event import Event
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

	thread_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	task_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("tasks.id", ondelete="SET NULL"),
		index=True,
	)
	sender_agent_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="SET NULL"),
		index=True,
	)
	sender_user_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="SET NULL"),
		index=True,
	)
	type: Mapped[MessageType] = mapped_column(
		StringEnum(MessageType),
		default=MessageType.USER,
	)
	content: Mapped[str] = mapped_column(Text())
	attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)
	read_by: Mapped[list[str]] = mapped_column(JSON, default=list)

	__mapper_args__ = {
		"polymorphic_on": type,
		"polymorphic_identity": "message",
	}

	thread: Mapped[Thread] = relationship(
		"Thread",
		back_populates="messages",
		innerjoin=True,
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


class UserMessage(Message):
	"""User message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.USER}


class AssistantMessage(Message):
	"""Assistant message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.ASSISTANT}


class ToolMessage(Message):
	"""Tool message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.TOOL}


class SystemMessage(Message):
	"""System message subclass."""

	__mapper_args__ = {"polymorphic_identity": MessageType.SYSTEM}
