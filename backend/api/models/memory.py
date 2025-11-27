"""Memory model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.message import Message
	from api.models.thread import Thread
	from api.models.user import User


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Persistent user knowledge entries."""

	__tablename__ = "memories"

	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	content: Mapped[str] = mapped_column(Text())
	source_thread_id: Mapped[str | None] = mapped_column(
		ForeignKey("threads.id", ondelete="SET NULL"),
	)
	source_message_id: Mapped[str | None] = mapped_column(
		ForeignKey("messages.id", ondelete="SET NULL"),
	)
	embedding: Mapped[bytes | None] = mapped_column(LargeBinary())
	last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	confidence: Mapped[float | None] = mapped_column(Float())
	category: Mapped[str | None] = mapped_column(String(50))

	owner: Mapped[User] = relationship(
		"User",
		back_populates="memories",
		lazy="selectin",
	)
	thread: Mapped[Thread | None] = relationship(
		"Thread",
		back_populates="memories",
		lazy="selectin",
	)
	message: Mapped[Message | None] = relationship(
		"Message",
		lazy="selectin",
	)
