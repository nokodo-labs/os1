"""user client model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.notification import NotificationPushSubscription
	from api.models.user import User


class UserClient(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""registered app/browser client identity for one user."""

	__tablename__ = "user_clients"
	__typeid_prefix__ = "uclt"
	__table_args__ = (
		UniqueConstraint("user_id", "client_key", name="uq_user_clients_user_key"),
	)

	user_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	client_key: Mapped[str] = mapped_column(String(128))
	name: Mapped[str | None] = mapped_column(String(120))
	user_agent: Mapped[str | None] = mapped_column(Text())
	info: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	preferences: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	user: Mapped[User] = relationship("User", back_populates="clients")
	push_subscriptions: Mapped[list[NotificationPushSubscription]] = relationship(
		"NotificationPushSubscription",
		back_populates="client",
		cascade="all, delete-orphan",
	)
