"""Provider schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.models.provider import ExposureStrategy, ProviderStatus
from api.schemas.common import MetadataModel


class ProviderBase(MetadataModel):
	"""Shared provider attributes."""

	name: str
	adapter_type: str
	base_url: str | None = None
	encrypted_api_key: str | None = None
	status: ProviderStatus = ProviderStatus.ENABLED
	exposure_strategy: ExposureStrategy = ExposureStrategy.AUTOFETCH
	manual_model_ids: list[str] = Field(default_factory=list)
	last_synced_at: datetime | None = None


class ProviderCreate(ProviderBase):
	"""Payload to create a provider."""

	pass


class ProviderUpdate(MetadataModel):
	"""Partial provider update payload."""

	adapter_type: str | None = None
	base_url: str | None = None
	encrypted_api_key: str | None = None
	status: ProviderStatus | None = None
	exposure_strategy: ExposureStrategy | None = None
	manual_model_ids: list[str] | None = None
	last_synced_at: datetime | None = None


class Provider(ProviderBase):
	"""Response schema."""

	id: str
	created_at: datetime
	updated_at: datetime
