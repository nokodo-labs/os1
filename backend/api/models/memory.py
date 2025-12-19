"""Memory model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.message import Message
	from api.models.user import User


class Memory(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Persistent user knowledge entries."""

	__tablename__ = "memories"
	__typeid_prefix__ = "mem"

	user_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	content: Mapped[str] = mapped_column(Text())
	source_message_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
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
	source_message: Mapped[Message | None] = relationship(
		"Message",
		lazy="selectin",
	)
