"""friendship model - represents friend connections between users.

upgrade path: the current schema stores one row per friendship pair (requester,
addressee) and uses an OR-query to look up either side. when the number of active
friendships grows large enough to make the OR-query a bottleneck, migrate to a
dual-row lookup table (one row per direction) so every lookup becomes a simple
equality scan. the service layer already encapsulates all queries through
_find_friendship / list_friends, so the migration is a single refactor point.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.user import User


class FriendshipStatus(StrEnum):
	PENDING = "pending"
	ACCEPTED = "accepted"
	DECLINED = "declined"
	REMOVED = "removed"


class Friendship(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""a directional friend request/relation.

	requester_id sends the request, addressee_id receives it.
	status tracks the lifecycle: pending -> accepted / declined / removed.
	once accepted, the relationship is mutual.

	see module docstring for the dual-row upgrade path.
	"""

	__tablename__ = "friendships"
	__typeid_prefix__ = "frnd"
	__table_args__ = (
		UniqueConstraint(
			"requester_id",
			"addressee_id",
			name="uq_friendship_pair",
		),
	)

	requester_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	addressee_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	status: Mapped[FriendshipStatus] = mapped_column(
		StringEnum(FriendshipStatus),
		default=FriendshipStatus.PENDING,
	)
	accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	requester: Mapped[User] = relationship(
		"User",
		foreign_keys=[requester_id],
		back_populates="sent_friend_requests",
	)
	addressee: Mapped[User] = relationship(
		"User",
		foreign_keys=[addressee_id],
		back_populates="received_friend_requests",
	)
	events: Mapped[list[FriendshipEvent]] = relationship(
		"FriendshipEvent",
		back_populates="friendship",
		order_by="FriendshipEvent.created_at",
		cascade="all, delete-orphan",
	)


class FriendshipEvent(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""append-only log of friendship status changes.

	the friendship table stores current state; this table preserves the full
	history. every transition (pending, accepted, declined, removed) is
	recorded here with the actor who triggered it.
	"""

	__tablename__ = "friendship_events"
	__typeid_prefix__ = "frev"

	friendship_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("friendships.id", ondelete="CASCADE"),
		index=True,
	)
	status: Mapped[FriendshipStatus] = mapped_column(
		StringEnum(FriendshipStatus),
	)
	actor_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
	)

	friendship: Mapped[Friendship] = relationship(
		"Friendship",
		back_populates="events",
	)
