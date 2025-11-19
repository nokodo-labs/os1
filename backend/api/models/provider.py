"""Provider configuration model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, TimestampMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.model import Model


class ProviderStatus(StrEnum):
	"""Operational state of a provider."""

	ENABLED = "enabled"
	DISABLED = "disabled"


class ExposureStrategy(StrEnum):
	"""How models are synchronized from providers."""

	AUTOFETCH = "autofetch_all"
	MANUAL = "manual"


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Configuration for external model providers."""

	__tablename__ = "providers"

	name: Mapped[str] = mapped_column(String(100), unique=True)
	adapter_type: Mapped[str] = mapped_column(String(100))
	base_url: Mapped[str | None] = mapped_column(String(255))
	encrypted_api_key: Mapped[str | None] = mapped_column(String(1024))
	status: Mapped[ProviderStatus] = mapped_column(
		Enum(ProviderStatus, name="provider_status"),
		default=ProviderStatus.ENABLED,
	)
	exposure_strategy: Mapped[ExposureStrategy] = mapped_column(
		Enum(ExposureStrategy, name="provider_exposure_strategy"),
		default=ExposureStrategy.AUTOFETCH,
	)
	manual_model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
	last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	models: Mapped[list[Model]] = relationship(
		"Model",
		back_populates="provider",
		cascade="all, delete-orphan",
	)
