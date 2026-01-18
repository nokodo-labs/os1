"""Settings document model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.user import User


class SettingsDocument(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Namespaced settings document.

	each namespace has a single system-wide document.
	"""

	__tablename__ = "settings_documents"
	__typeid_prefix__ = "setdoc"

	namespace: Mapped[str] = mapped_column(
		String(100),
		nullable=False,
		doc="settings section key, e.g. 'ai_defaults', 'ui', 'branding'",
	)
	data: Mapped[dict[str, Any]] = mapped_column(
		JSONB,
		default=dict,
		doc="the actual settings values (partial, merged with defaults on read)",
	)
	version: Mapped[int] = mapped_column(
		Integer,
		default=1,
		doc="optimistic locking version, incremented on each update",
	)
	updated_by_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
	)

	updated_by: Mapped[User | None] = relationship("User", foreign_keys=[updated_by_id])

	__table_args__ = (
		Index("ix_settings_documents_namespace", "namespace", unique=True),
	)
