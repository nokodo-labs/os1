"""Provider configuration model."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import (
	MetadataJSONMixin,
	StringEnum,
	TimestampMixin,
	UUIDPrimaryKeyMixin,
)


if TYPE_CHECKING:
	from api.models.model import Model


class ProviderStatus(StrEnum):
	"""Operational state of a provider."""

	ENABLED = "enabled"
	DISABLED = "disabled"


class ProviderType(StrEnum):
	"""Type of provider deployment."""

	LOCAL = "local"
	EXTERNAL = "external"


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""Configuration for external model providers."""

	__tablename__ = "providers"

	name: Mapped[str] = mapped_column(String(100), unique=True)
	adapter_type: Mapped[str] = mapped_column(String(100))
	provider_type: Mapped[ProviderType] = mapped_column(
		StringEnum(ProviderType),
		default=ProviderType.EXTERNAL,
	)
	base_url: Mapped[str | None] = mapped_column(String(255))
	encrypted_api_key: Mapped[str | None] = mapped_column(String(1024))
	model_prefix: Mapped[str | None] = mapped_column(String(50))
	additional_headers: Mapped[dict | None] = mapped_column(JSON)
	status: Mapped[ProviderStatus] = mapped_column(
		StringEnum(ProviderStatus),
		default=ProviderStatus.ENABLED,
	)
	is_autofetch_enabled: Mapped[bool] = mapped_column(default=True)
	last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	models: Mapped[list[Model]] = relationship(
		"Model",
		back_populates="provider",
		cascade="all, delete-orphan",
	)

	@property
	def manual_models(self) -> list[Model]:
		"""Return models that were manually created."""
		return [m for m in self.models if not m.is_autofetched]

	@property
	def autofetched_models(self) -> list[Model]:
		"""Return models that were automatically fetched."""
		return [m for m in self.models if m.is_autofetched]
