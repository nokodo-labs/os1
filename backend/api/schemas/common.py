"""Shared schema utilities."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from pydantic.experimental.missing_sentinel import MISSING

from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from typing_extensions import Sentinel as MissingType
else:
	MissingType = MISSING


def is_private_metadata_key(key: str) -> bool:
	"""return True for backend-private metadata keys that must not leave the api."""
	return key.startswith("_")


def sanitize_metadata(metadata: JSONObject | None) -> JSONObject:
	"""return metadata safe to include in api/sse payloads."""
	if not metadata:
		return {}
	return {
		key: value
		for key, value in metadata.items()
		if not is_private_metadata_key(key)
	}


class ORMModel(BaseModel):
	"""Base schema with ORM compatibility."""

	model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MetadataModel(ORMModel):
	"""Adds metadata support for models using MetadataJSONMixin."""

	metadata: JSONObject = Field(default_factory=dict, alias="metadata_")

	@field_validator("metadata", mode="before")
	@classmethod
	def _coerce_none_metadata(cls, value: object) -> object:
		if value is None:
			return {}
		return value

	@field_serializer("metadata")
	def serialize_public_metadata(self, metadata: JSONObject) -> JSONObject:
		"""serialize only metadata that belongs on the public api surface."""
		return sanitize_metadata(metadata)


class MetadataUpdateModel(ORMModel):
	"""Adds metadata support for update schemas."""

	metadata: JSONObject | MissingType = Field(default=MISSING, alias="metadata_")


class TimestampedModel(ORMModel):
	"""Adds standard timestamp fields."""

	created_at: datetime
	updated_at: datetime
