"""notification model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	Boolean,
	DateTime,
	ForeignKey,
	Index,
	String,
	UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.event import Event
	from api.models.user import User


class Notification(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""persistent delivery guarantee for important events."""

	__tablename__ = "notifications"
	__typeid_prefix__ = "notif"
	__table_args__ = (
		UniqueConstraint("delivery_key", name="uq_notifications_delivery_key"),
		Index("ix_notifications_notify_at", "notify_at"),
	)

	user_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	event_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("events.id", ondelete="CASCADE"),
		index=True,
	)
	read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	dismissed: Mapped[bool] = mapped_column(Boolean(), default=False)
	delivery_key: Mapped[str | None] = mapped_column(String(512))
	notify_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	user: Mapped[User] = relationship(
		"User",
		back_populates="notifications",
	)
	event: Mapped[Event] = relationship(
		"Event",
		back_populates="notifications",
		innerjoin=True,
	)
