"""Agent model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from api.schemas.agent import AgentConfig


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.file import File
	from api.models.message import Message
	from api.models.model import Model
	from api.models.thread_participant import ThreadParticipant


class Agent(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""User-facing AI persona with configuration."""

	__tablename__ = "agents"
	__typeid_prefix__ = "agent"

	name: Mapped[str] = mapped_column(String(100), unique=True)
	description: Mapped[str | None] = mapped_column(Text())
	system_prompt: Mapped[str | None] = mapped_column(Text())
	plugin_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
	config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
	model_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("models.id", ondelete="SET NULL"),
	)
	profile_image_file_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("files.id", ondelete="SET NULL"),
	)
	profile_image_url: Mapped[str | None] = mapped_column(String(2048))

	model: Mapped[Model | None] = relationship(
		"Model",
		back_populates="agents",
	)
	profile_image_file: Mapped[File | None] = relationship(
		"File",
		foreign_keys=[profile_image_file_id],
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="agent",
		cascade="all, delete-orphan",
	)
	messages: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="sender_agent",
	)
	thread_participants: Mapped[list[ThreadParticipant]] = relationship(
		"ThreadParticipant",
		back_populates="agent",
		cascade="all, delete-orphan",
	)

	@property
	def parsed_config(self) -> AgentConfig:
		"""typed view of ``self.config``.

		single canonical parse point so callers never need to re-validate
		the raw JSONB. unknown keys round-trip via ``AgentConfig`` extras.
		"""
		return AgentConfig.model_validate(self.config or {})
