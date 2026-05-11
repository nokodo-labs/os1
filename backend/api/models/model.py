"""Model configuration."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


MODEL_TYPEID_PREFIX = "model"


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.provider import Provider


class InputModality(StrEnum):
	"""Supported input modalities for models."""

	TEXT = "text"
	IMAGES = "images"
	AUDIO = "audio"
	VIDEO = "video"


class ModelType(StrEnum):
	"""Supported model categories."""

	CHAT_MODEL = "chat_model"
	EMBEDDING = "embedding"
	IMAGE = "image"
	AUDIO = "audio"
	VIDEO = "video"


class Model(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Model entry tied to an upstream provider."""

	__tablename__ = "models"
	__typeid_prefix__ = MODEL_TYPEID_PREFIX

	provider_id: Mapped[str] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("providers.id", ondelete="CASCADE"),
		index=True,
	)
	name: Mapped[str] = mapped_column(String(150))
	display_name: Mapped[str | None] = mapped_column(String(150))
	model_type: Mapped[ModelType] = mapped_column(
		StringEnum(ModelType),
		default=ModelType.CHAT_MODEL,
	)
	input_modalities: Mapped[list[str]] = mapped_column(
		JSONB,
		default=list,
		server_default="[]",
	)
	endpoint: Mapped[str | None] = mapped_column(String(255))
	adapter: Mapped[str | None] = mapped_column(String(100))
	capabilities: Mapped[list[str]] = mapped_column(JSONB, default=list)
	context_window: Mapped[int | None] = mapped_column(Integer())
	input_cost: Mapped[float | None] = mapped_column(Float())
	output_cost: Mapped[float | None] = mapped_column(Float())
	enabled: Mapped[bool] = mapped_column(default=True)
	is_autofetched: Mapped[bool] = mapped_column(default=False)

	provider: Mapped[Provider] = relationship(
		"Provider",
		back_populates="models",
		innerjoin=True,
	)
	agents: Mapped[list[Agent]] = relationship(
		"Agent",
		back_populates="model",
	)
