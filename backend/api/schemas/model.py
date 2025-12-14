"""Model schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.models.model import ModelType
from api.schemas.common import MetadataModel


class ModelBase(MetadataModel):
	"""Shared model attributes."""

	name: str
	display_name: str | None = None
	model_type: ModelType = ModelType.LLM
	endpoint: str | None = None
	capabilities: list[str] = Field(default_factory=list)
	context_window: int | None = None
	input_cost: float | None = None
	output_cost: float | None = None
	enabled: bool = True
	is_autofetched: bool = False


class ModelCreate(ModelBase):
	"""Payload to register a model."""

	provider_id: str


class Model(ModelBase):
	"""Response schema."""

	id: str
	provider_id: str
	created_at: datetime
	updated_at: datetime


class ModelUpdate(MetadataModel):
	"""Payload to update a model."""

	name: str | None = None
	display_name: str | None = None
	model_type: ModelType | None = None
	endpoint: str | None = None
	capabilities: list[str] | None = None
	context_window: int | None = None
	input_cost: float | None = None
	output_cost: float | None = None
	enabled: bool | None = None
	is_autofetched: bool | None = None
