"""model schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from api.models.model import InputModality, ModelType
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)


class ModelListFilters(BaseModel):
	"""filters for listing models."""

	provider_id: str | None = None


class ModelBase(MetadataModel):
	"""shared model attributes."""

	name: str
	display_name: str | None = None
	model_type: ModelType = ModelType.CHAT_MODEL
	endpoint: str | None = None
	adapter: str | None = None
	capabilities: list[str] = Field(default_factory=list)
	context_window: int | None = None
	input_cost: float | None = None
	output_cost: float | None = None
	enabled: bool = True
	is_autofetched: bool = False


class ModelCreate(ModelBase):
	"""payload to register a model."""

	input_modalities: list[InputModality] | None = None
	provider_id: str


class Model(ModelBase, TimestampedModel):
	"""response schema."""

	input_modalities: list[InputModality]
	id: str
	provider_id: str


class ModelUpdate(MetadataUpdateModel):
	"""payload to update a model."""

	name: str | MissingType = MISSING
	display_name: str | None | MissingType = MISSING
	model_type: ModelType | MissingType = MISSING
	input_modalities: list[InputModality] | MissingType = MISSING
	endpoint: str | None | MissingType = MISSING
	adapter: str | None | MissingType = MISSING
	capabilities: list[str] | MissingType = MISSING
	context_window: int | None | MissingType = MISSING
	input_cost: float | None | MissingType = MISSING
	output_cost: float | None | MissingType = MISSING
	enabled: bool | MissingType = MISSING
	is_autofetched: bool | MissingType = MISSING
