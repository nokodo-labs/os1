"""provider schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints, field_validator

from api.models.provider import ProviderStatus, ProviderType
from api.schemas.common import MetadataModel, MetadataUpdateModel, TimestampedModel


class ProviderBase(MetadataModel):
	"""shared provider attributes."""

	name: Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
	adapter_type: str
	provider_type: ProviderType = ProviderType.EXTERNAL
	base_url: str | None = None
	encrypted_api_key: str | None = None
	additional_headers: dict[str, str] | None = None
	status: ProviderStatus = ProviderStatus.ENABLED
	is_autofetch_enabled: bool = True
	last_synced_at: datetime | None = None


class ProviderCreate(ProviderBase):
	"""payload to create a provider."""

	api_key: str | None = None


class ProviderUpdate(MetadataUpdateModel):
	"""partial provider update payload."""

	name: str | None = None
	adapter_type: str | None = None
	provider_type: ProviderType | None = None
	base_url: str | None = None
	api_key: str | None = None
	encrypted_api_key: str | None = None
	additional_headers: dict[str, str] | None = None
	status: ProviderStatus | None = None
	is_autofetch_enabled: bool | None = None
	last_synced_at: datetime | None = None


class Provider(ProviderBase, TimestampedModel):
	"""response schema."""

	id: str

	@field_validator("name", mode="before")
	@classmethod
	def _coerce_empty_name(cls, v: str) -> str:
		"""legacy rows may have empty name; provide a fallback for the response."""
		if isinstance(v, str) and not v.strip():
			return "(unnamed provider)"
		return v
