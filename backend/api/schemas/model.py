"""model schemas."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from api.models.model import InputModality, ModelType
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from nokodo_ai.utils.typeid import TypeID


class ModelListFilters(BaseModel):
	"""filters for listing models."""

	provider_id: TypeID | None = None


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


class ModelCreate(ModelBase, ForbidExtraModel):
	"""payload to register a model."""

	input_modalities: list[InputModality] | None = None
	provider_id: TypeID

	@model_validator(mode="after")
	def _require_embedding_context_window(self) -> Self:
		if self.model_type == ModelType.EMBEDDING and not self.context_window:
			raise ValueError("embedding models require a context_window")
		return self


class Model(ModelBase, TimestampedModel):
	"""response schema."""

	input_modalities: list[InputModality]
	id: TypeID
	provider_id: TypeID


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
