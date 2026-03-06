"""Plugin model.

This represents a user-defined plugin module uploaded by an admin.
Plugins can be tools, filters, or hooks that extend agent capabilities.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule


class PluginType(StrEnum):
	"""Type of plugin."""

	TOOL = "tool"
	FILTER = "filter"
	HOOK = "hook"


class Plugin(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Admin-managed plugin definition persisted in the database."""

	__tablename__ = "plugins"
	__typeid_prefix__ = "plugin"

	name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
	description: Mapped[str | None] = mapped_column(Text())
	type: Mapped[PluginType] = mapped_column(StringEnum(PluginType))
	author: Mapped[str | None] = mapped_column(String(150))
	version: Mapped[str | None] = mapped_column(String(50))
	source_code: Mapped[str] = mapped_column(Text())

	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="plugin",
		cascade="all, delete-orphan",
	)
