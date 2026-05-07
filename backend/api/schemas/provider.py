"""provider schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import StringConstraints, field_validator

from api.models.provider import ProviderStatus, ProviderType
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)


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


class ProviderCreate(ProviderBase):
	"""payload to create a provider."""

	api_key: str | None = None


class ProviderUpdate(MetadataUpdateModel):
	"""partial provider update payload."""

	name: str | MissingType = MISSING
	adapter_type: str | MissingType = MISSING
	provider_type: ProviderType | MissingType = MISSING
	base_url: str | None | MissingType = MISSING
	api_key: str | None | MissingType = MISSING
	encrypted_api_key: str | None | MissingType = MISSING
	additional_headers: dict[str, str] | None | MissingType = MISSING
	status: ProviderStatus | MissingType = MISSING
	is_autofetch_enabled: bool | MissingType = MISSING


class Provider(ProviderBase, TimestampedModel):
	"""response schema."""

	id: str
	last_synced_at: datetime | None = None

	@field_validator("name", mode="before")
	@classmethod
	def _coerce_empty_name(cls, v: str) -> str:
		"""legacy rows may have empty name; provide a fallback for the response."""
		if isinstance(v, str) and not v.strip():
			return "(unnamed provider)"
		return v
