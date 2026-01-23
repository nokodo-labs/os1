"""embedding model building and resolution for the api."""

from __future__ import annotations

from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import Model, ModelType
from api.models.provider import Provider
from api.settings import settings
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.typeid import TypeID


def build_sdk_adapter_config(
	provider: Provider,
	adapter_type: str,
) -> dict[str, object]:
	"""build a fully explicit SDK adapter config dict from an ORM Provider."""
	adapter_config: dict[str, object] = {
		"type": adapter_type,
	}
	if provider.base_url is not None and provider.base_url.strip() != "":
		adapter_config["base_url"] = provider.base_url
	if provider.api_key is not None:
		adapter_config["api_key"] = provider.api_key
	return adapter_config


def build_embedding_model(model: Model) -> EmbeddingModel:
	"""create an SDK EmbeddingModel from an ORM model."""
	if model.model_type != ModelType.EMBEDDING:
		raise ValueError(f"model {model.id} is not an embedding model")

	adapter_type = model.provider.adapter_type
	if model.adapter is not None:
		adapter_type += f".{model.adapter}"

	adapter_config = build_sdk_adapter_config(model.provider, adapter_type=adapter_type)
	return EmbeddingModel.create(
		model.name,
		adapter=adapter_config,
	)


@overload
async def resolve_embedding_model(
	session: AsyncSession,
	model_id: TypeID,
) -> Model: ...


@overload
async def resolve_embedding_model(
	session: AsyncSession,
	model_id: None = None,
) -> Model: ...


async def resolve_embedding_model(
	session: AsyncSession,
	model_id: TypeID | None = None,
) -> Model:
	"""resolve an embedding model by ID, or fall back to default."""
	if model_id is None:
		model_id = await _get_default_embedding_model_id(session)

	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if model is None:
		raise HTTPException(status_code=404, detail="model not found")
	return model


async def _get_default_embedding_model_id(session: AsyncSession) -> TypeID:
	"""internal: resolve default embedding model ID from settings or auto-detect."""
	configured = settings.assets.default_embedding_model_id
	if configured is not None and configured.strip():
		try:
			return TypeID(configured)
		except Exception as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="assets.default_embedding_model_id is not a valid model ID",
			) from e

	stmt = (
		select(Model.id)
		.where(Model.model_type == ModelType.EMBEDDING)
		.where(Model.enabled.is_(True))
		.order_by(Model.created_at.desc())
	)
	result = await session.execute(stmt)
	ids = [TypeID(row[0]) for row in result.all()]

	match len(ids):
		case 1:
			return ids[0]
		case 0:
			raise HTTPException(409, detail="no embedding models are configured")
		case _:
			raise HTTPException(409, detail="default embedding model is not configured")
