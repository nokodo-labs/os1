"""Notification model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.event import Event
	from api.models.user import User


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
	"""Persistent delivery guarantee for important events."""

	__tablename__ = "notifications"

	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
	event_id: Mapped[str] = mapped_column(
		ForeignKey("events.id", ondelete="CASCADE"),
		index=True,
	)
	read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	dismissed: Mapped[bool] = mapped_column(Boolean(), default=False)

	user: Mapped[User] = relationship(
		"User",
		back_populates="notifications",
	)
	event: Mapped[Event] = relationship(
		"Event",
		back_populates="notifications",
		innerjoin=True,
	)
