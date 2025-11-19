"""Message model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.event import Event
	from api.models.task import Task
	from api.models.thread import Thread


class MessageRole(StrEnum):
	"""Available message roles."""

	USER = "user"
	ASSISTANT = "assistant"
	TOOL = "tool"
	SYSTEM = "system"


class Message(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Stores timeline entries for a thread."""

	__tablename__ = "messages"

	thread_id: Mapped[str] = mapped_column(
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	task_id: Mapped[str | None] = mapped_column(
		ForeignKey("tasks.id", ondelete="SET NULL"),
		index=True,
	)
	agent_id: Mapped[str | None] = mapped_column(
		ForeignKey("agents.id", ondelete="SET NULL"),
		index=True,
	)
	role: Mapped[MessageRole] = mapped_column(
		Enum(MessageRole, name="message_role"),
		default=MessageRole.USER,
	)
	content: Mapped[str] = mapped_column(Text())
	attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
	token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON)

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
	agent: Mapped[Agent | None] = relationship(
		"Agent",
		back_populates="messages",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="message",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
