"""prompt model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


PROMPT_TYPEID_PREFIX = "prompt"


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule


class Prompt(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""reusable, composable prompt template snippet."""

	__tablename__ = "prompts"
	__typeid_prefix__ = PROMPT_TYPEID_PREFIX

	command: Mapped[str] = mapped_column(String(120), unique=True)
	content: Mapped[str] = mapped_column(Text())

	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="prompt",
		cascade="all, delete-orphan",
	)
