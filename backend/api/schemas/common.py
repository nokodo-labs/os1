"""Shared schema utilities."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


type ApiJSONObject = dict[str, object]


class ORMModel(BaseModel):
	"""Base schema with ORM compatibility."""

	model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MetadataModel(ORMModel):
	"""Adds metadata support for models using MetadataJSONMixin."""

	metadata: ApiJSONObject = Field(default_factory=dict, alias="metadata_")

	@field_validator("metadata", mode="before")
	@classmethod
	def _coerce_none_metadata(cls, value: object) -> object:
		if value is None:
			return {}
		return value


class TimestampedModel(ORMModel):
	"""Adds standard timestamp fields."""

	created_at: datetime
	updated_at: datetime
