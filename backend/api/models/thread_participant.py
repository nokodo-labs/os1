"""ThreadParticipant model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	Boolean,
	CheckConstraint,
	DateTime,
	ForeignKey,
	Index,
	String,
	func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.message import Message
	from api.models.thread import Thread
	from api.models.user import User


class ThreadParticipant(TypeIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""per-user thread state, or an agent's presence in a thread"""

	__tablename__ = "thread_participants"
	__typeid_prefix__ = "tpart"

	thread_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	user_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	agent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="CASCADE"),
		index=True,
	)

	# unused: reserved for future per-thread member roles (that can't flow through ACL).
	membership_role: Mapped[str | None] = mapped_column(String(50))
	joined_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)

	# per-user thread state (user rows only; meaningless on agent rows).
	last_read_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
	)
	muted: Mapped[bool] = mapped_column(Boolean, default=False)
	pinned: Mapped[bool] = mapped_column(Boolean, default=False)
	archived: Mapped[bool] = mapped_column(Boolean, default=False)

	# per-thread agent behavior (agent rows only; meaningless on user rows).
	invoke_on_mention: Mapped[bool | None] = mapped_column(Boolean)
	"""whether mentioning this agent here also invokes it; null inherits the
	agent's own setting."""

	__table_args__ = (
		CheckConstraint(
			"(user_id IS NULL) <> (agent_id IS NULL)",
			name="ck_thread_participants_exactly_one_principal",
		),
		# one row per (thread, user) and (thread, agent).
		Index(
			"uq_thread_participants_user",
			"thread_id",
			"user_id",
			unique=True,
			postgresql_where=(user_id.is_not(None)),
		),
		Index(
			"uq_thread_participants_agent",
			"thread_id",
			"agent_id",
			unique=True,
			postgresql_where=(agent_id.is_not(None)),
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
