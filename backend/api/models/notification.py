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
	Text,
	UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from nokodo_ai.types.json import JSONArray, JSONObject
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.event import Event
	from api.models.user import User
	from api.models.user_client import UserClient


class Notification(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""persistent delivery guarantee for important events."""

	__tablename__ = "notifications"
	__typeid_prefix__ = "notif"
	__table_args__ = (
		UniqueConstraint("delivery_key", name="uq_notifications_delivery_key"),
		Index("ix_notifications_notify_at", "notify_at"),
		Index("ix_notifications_expires_at", "expires_at"),
	)

	title: Mapped[str] = mapped_column(String(200))
	body: Mapped[str | None] = mapped_column(Text())
	icon_url: Mapped[str | None] = mapped_column(Text())
	image_url: Mapped[str | None] = mapped_column(Text())
	badge_url: Mapped[str | None] = mapped_column(Text())
	action_url: Mapped[str | None] = mapped_column(Text())
	tag: Mapped[str | None] = mapped_column(String(128))
	data: Mapped[JSONObject] = mapped_column(JSONB, default=dict)
	actions: Mapped[JSONArray] = mapped_column(JSONB, default=list)
	require_interaction: Mapped[bool | None] = mapped_column(Boolean())
	silent: Mapped[bool | None] = mapped_column(Boolean())
	renotify: Mapped[bool | None] = mapped_column(Boolean())
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
	expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	user: Mapped[User] = relationship(
		"User",
		back_populates="notifications",
	)
	event: Mapped[Event] = relationship(
		"Event",
		back_populates="notifications",
		innerjoin=True,
	)


class NotificationPushSubscription(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""web push subscription registered by one user client."""

	__tablename__ = "notification_push_subscriptions"
	__typeid_prefix__ = "npsub"
	__table_args__ = (
		UniqueConstraint(
			"endpoint", name="uq_notification_push_subscriptions_endpoint"
		),
	)

	client_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("user_clients.id", ondelete="CASCADE"),
		index=True,
	)
	endpoint: Mapped[str] = mapped_column(Text())
	p256dh: Mapped[str] = mapped_column(Text())
	auth: Mapped[str] = mapped_column(Text())
	expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	client: Mapped[UserClient] = relationship(
		"UserClient",
		back_populates="push_subscriptions",
	)
