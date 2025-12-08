"""Agent model."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import (
	MetadataJSONMixin,
	StringEnum,
	TimestampMixin,
	UUIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.acl import AccessControlEntry
	from api.models.message import Message
	from api.models.model import Model


class AgentVisibility(StrEnum):
	"""Controls who can view an agent."""

	PUBLIC = "public"
	PRIVATE = "private"
	ADMIN = "admin-only"


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""User-facing AI persona with configuration."""

	__tablename__ = "agents"

	name: Mapped[str] = mapped_column(String(100), unique=True)
	description: Mapped[str | None] = mapped_column(Text())
	system_prompt: Mapped[str | None] = mapped_column(Text())
	visibility: Mapped[AgentVisibility] = mapped_column(
		StringEnum(AgentVisibility),
		default=AgentVisibility.PUBLIC,
	)
	tool_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
	config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	model_id: Mapped[str | None] = mapped_column(
		ForeignKey("models.id", ondelete="SET NULL"),
	)

	model: Mapped[Model | None] = relationship(
		"Model",
		back_populates="agents",
	)
	access_control_entries: Mapped[list[AccessControlEntry]] = relationship(
		"AccessControlEntry",
		back_populates="agent",
		cascade="all, delete-orphan",
	)
	messages: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="sender_agent",
	)
