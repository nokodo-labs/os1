"""Shared schema utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
	"""Base schema with ORM compatibility."""

	model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MetadataModel(ORMModel):
	"""Adds metadata support for models using MetadataJSONMixin."""

	metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_")


class TimestampedModel(ORMModel):
	"""Adds standard timestamp fields."""

	created_at: datetime
	updated_at: datetime
