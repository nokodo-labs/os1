"""embedding model building and resolution for the api."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import Model, ModelType
from api.models.provider import Provider
from nokodo_ai.adapters.embeddings import resolve_embeddings_adapter
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.typeid import TypeID


def build_sdk_adapter_config(
	provider: Provider,
	*,
	adapter_type: str,
) -> dict[str, object]:
	"""build a fully explicit sdk adapter config dict from an orm Provider."""
	adapter_config: dict[str, object] = {
		"type": adapter_type,
	}
	if provider.base_url is not None and provider.base_url.strip() != "":
		adapter_config["base_url"] = provider.base_url
	if provider.api_key is not None:
		adapter_config["api_key"] = provider.api_key
	return adapter_config


def build_embedding_model(model: Model) -> EmbeddingModel:
	"""create an sdk EmbeddingModel with fully explicit adapter configuration."""
	if model.model_type != ModelType.EMBEDDING:
		raise ValueError(f"model {model.id} is not an embedding model")

	provider_key = model.provider.adapter_type
	if not provider_key:
		raise ValueError("provider adapter_type is empty")

	variant = model.adapter
	adapter_type = resolve_embeddings_adapter(provider_key, variant)
	if adapter_type is None:
		raise ValueError(f"unknown embedding provider: {provider_key}")

	adapter_config = build_sdk_adapter_config(model.provider, adapter_type=adapter_type)
	return EmbeddingModel.model_validate(
		{
			"provider": provider_key,
			"variant": variant,
			"model_name": model.name,
			"adapter": adapter_config,
		}
	)


async def resolve_embedding_model(
	session: AsyncSession,
	model_id: TypeID,
) -> EmbeddingModel:
	"""resolve and build an sdk EmbeddingModel from a model id."""
	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if model is None:
		raise HTTPException(status_code=404, detail="model not found")
	return build_embedding_model(model)
