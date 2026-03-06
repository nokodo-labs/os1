"""block model - user-level blocks, independent of friendships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.user import User


class Block(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""a user-level block.

	blocks are independent of friendship state - a block can exist with or
	without a prior friendship. when a block exists, the blocker cannot
	receive friend requests from the blocked user and vice versa.
	"""

	__tablename__ = "blocks"
	__typeid_prefix__ = "blck"
	__table_args__ = (
		UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),
	)

	blocker_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	blocked_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)

	blocker: Mapped[User] = relationship(
		"User",
		foreign_keys=[blocker_id],
	)
	blocked: Mapped[User] = relationship(
		"User",
		foreign_keys=[blocked_id],
	)
