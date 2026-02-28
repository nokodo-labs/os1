"""model schemas."""

from __future__ import annotations

from pydantic import Field

from api.models.model import InputModality, ModelType
from api.schemas.common import MetadataModel, MetadataUpdateModel, TimestampedModel


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

	name: str | None = None
	display_name: str | None = None
	model_type: ModelType | None = None
	input_modalities: list[InputModality] | None = None
	endpoint: str | None = None
	adapter: str | None = None
	capabilities: list[str] | None = None
	context_window: int | None = None
	input_cost: float | None = None
	output_cost: float | None = None
	enabled: bool | None = None
	is_autofetched: bool | None = None
