"""Prompt model."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


class Prompt(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Reusable, composable prompt template snippet."""

	__tablename__ = "prompts"
	__typeid_prefix__ = "prompt"

	command: Mapped[str] = mapped_column(String(120), unique=True)
	content: Mapped[str] = mapped_column(Text())
