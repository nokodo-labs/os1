"""ThreadParticipant model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.message import Message
	from api.models.thread import Thread
	from api.models.user import User


class ThreadParticipant(TypeIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""Normalized participant state for a thread."""

	__tablename__ = "thread_participants"
	__typeid_prefix__ = "tpart"

	thread_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	user_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	agent_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="CASCADE"),
		index=True,
	)

	membership_role: Mapped[str | None] = mapped_column(String(50))
	joined_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)
	left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_read_message_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
	)

	__table_args__ = (
		CheckConstraint(
			"(user_id IS NULL) <> (agent_id IS NULL)",
			name="ck_thread_participants_exactly_one_principal",
		),
	)

	thread: Mapped[Thread] = relationship(
		"Thread",
		back_populates="participants",
		innerjoin=True,
	)
	user: Mapped[User | None] = relationship(
		"User",
		back_populates="thread_participants",
	)
	agent: Mapped[Agent | None] = relationship(
		"Agent",
		back_populates="thread_participants",
	)
	last_read_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys=[last_read_message_id],
	)
