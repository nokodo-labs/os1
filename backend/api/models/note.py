"""Note model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	SoftDeleteMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.user import User


class Note(
	TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, SoftDeleteMixin, Base
):
	"""Simple markdown notes with labels."""

	__tablename__ = "notes"
	__typeid_prefix__ = "note"

	user_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	title: Mapped[str] = mapped_column(String(255))
	content: Mapped[str] = mapped_column(Text(), default="")
	labels: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="notes",
		lazy="selectin",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="note",
		cascade="all, delete-orphan",
	)
