"""user session model."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.user import User
	from api.models.user_client import UserClient


SESSION_TYPEID_PREFIX = "sess"


class UserSession(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""server-side login session backing one refresh token chain."""

	__tablename__ = "user_sessions"
	__typeid_prefix__ = SESSION_TYPEID_PREFIX
	__table_args__ = (
		Index("ix_user_sessions_revoked_at_expires_at", "revoked_at", "expires_at"),
	)

	user_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	client_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("user_clients.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	current_jti: Mapped[str] = mapped_column(String(64))
	prev_jti: Mapped[str | None] = mapped_column(String(64))
	rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
	revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	user_agent: Mapped[str | None] = mapped_column(Text())

	user: Mapped[User] = relationship("User", back_populates="sessions")
	client: Mapped[UserClient | None] = relationship("UserClient")

	@property
	def is_active(self) -> bool:
		"""whether the session is neither revoked nor expired."""
		return self.revoked_at is None and self.expires_at > datetime.now(UTC)
