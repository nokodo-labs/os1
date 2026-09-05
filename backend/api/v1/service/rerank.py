"""reranker model building and resolution for the api."""

import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.models.model import Model, ModelType
from api.redis import on_invalidation
from api.runtime import on_settings_reload
from api.settings import settings
from api.v1.service.embeddings import build_sdk_adapter_config
from nokodo_ai.rerankers import Reranker
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# process-level cache - resolved once, reused for every rerank call.
_cached_reranker: Reranker | None = None


def reset_rerank_model_cache() -> None:
	"""invalidate the cached reranker (e.g. after settings change)."""
	global _cached_reranker
	_cached_reranker = None


on_invalidation("rerank_model", reset_rerank_model_cache)
on_settings_reload(reset_rerank_model_cache)


def build_reranker(model: Model) -> Reranker:
	"""create an SDK Reranker from an ORM model."""
	if model.model_type != ModelType.RERANKER:
		raise ValueError(f"model {model.id} is not a reranker model")

	adapter_type = model.provider.adapter_type
	if model.adapter is not None:
		adapter_type += f".{model.adapter}"

	adapter_config = build_sdk_adapter_config(model.provider, adapter_type=adapter_type)
	return Reranker.create(
		model.name,
		adapter=adapter_config,
	)


async def get_reranker(session: AsyncSession | None = None) -> Reranker:
	"""return the cached Reranker, resolving from DB on first call.

	when session is None and the cache is cold, opens its own short-lived
	session for the DB lookup.
	"""
	global _cached_reranker
	if _cached_reranker is not None:
		return _cached_reranker
	if session is None:
		async with async_session_local() as owned:
			return await get_reranker(owned)
	model = await resolve_rerank_model(session)
	_cached_reranker = build_reranker(model)
	logger.info(
		"cached reranker model: %s (provider=%s)",
		model.name,
		model.provider.name,
	)
	return _cached_reranker


async def resolve_rerank_model(
	session: AsyncSession,
	model_id: TypeID | None = None,
) -> Model:
	"""resolve a reranker model by ID, or fall back to default."""
	if model_id is None:
		model_id = await _get_default_rerank_model_id(session)

	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if model is None:
		raise HTTPException(status_code=404, detail="model not found")
	return model


async def _get_default_rerank_model_id(session: AsyncSession) -> TypeID:
	"""internal: resolve default reranker model ID from settings or auto-detect."""
	configured = settings.assets.rerank.default_model_id
	if configured is not None and configured.strip():
		try:
			return TypeID(configured)
		except Exception as e:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="assets.rerank.default_model_id is not a valid model ID",
			) from e

	stmt = (
		select(Model.id)
		.where(Model.model_type == ModelType.RERANKER)
		.where(Model.enabled.is_(True))
		.order_by(Model.created_at.desc())
	)
	result = await session.execute(stmt)
	ids = [TypeID(row[0]) for row in result.all()]

	match len(ids):
		case 1:
			return ids[0]
		case 0:
			raise HTTPException(409, detail="no reranker models are configured")
		case _:
			raise HTTPException(409, detail="default reranker model is not configured")
