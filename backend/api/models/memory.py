"""Memory model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.message import Message
	from api.models.user import User


class Memory(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Persistent user knowledge entries."""

	__tablename__ = "memories"
	__typeid_prefix__ = "mem"
	__table_args__ = (
		Index(
			"idx_memories_content_trgm",
			"content",
			postgresql_using="gin",
			postgresql_ops={"content": "gin_trgm_ops"},
		),
	)

	user_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	content: Mapped[str] = mapped_column(Text())
	source_message_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
		index=True,
	)
	embedding: Mapped[bytes | None] = mapped_column(LargeBinary())
	last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	confidence: Mapped[float | None] = mapped_column(Float())
	tags: Mapped[list[str] | None] = mapped_column(ARRAY(String))

	owner: Mapped[User] = relationship(
		"User",
		back_populates="memories",
		lazy="selectin",
	)
	source_message: Mapped[Message | None] = relationship(
		"Message",
		lazy="selectin",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="memory",
		cascade="all, delete-orphan",
	)
