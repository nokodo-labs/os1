"""embedding model building and resolution for the api."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import Model, ModelType
from api.models.provider import Provider
from api.redis import on_invalidation
from api.settings import settings
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# process-level cache - resolved once, reused for every embed call.
# avoids a DB round-trip + object construction on every search.
_cached_embedding_model: EmbeddingModel | None = None


def reset_embedding_model_cache() -> None:
	"""invalidate the cached embedding model (e.g. after settings change)."""
	global _cached_embedding_model
	_cached_embedding_model = None


# self-register for cross-worker invalidation when the embedding settings
# change. main.py only needs to start the subscriber; modules own their
# own reset hook registration.
on_invalidation("embedding_model", reset_embedding_model_cache)


async def _get_embedding_model(session: AsyncSession) -> EmbeddingModel:
	"""return the cached EmbeddingModel, resolving from DB on first call."""
	global _cached_embedding_model
	if _cached_embedding_model is not None:
		return _cached_embedding_model
	model = await resolve_embedding_model(session)
	_cached_embedding_model = build_embedding_model(model)
	logger.info(
		"cached embedding model: %s (provider=%s)",
		model.name,
		model.provider.name,
	)
	return _cached_embedding_model


async def embed_text(text: str, session: AsyncSession) -> list[float]:
	"""embed a single text string."""
	model = await _get_embedding_model(session)
	extra: dict[str, object] = {
		"model": model.model_name,
		"text_count": 1,
		"input_chars": len(text),
	}
	started = time.perf_counter()
	logger.info("embedding call started", extra=extra)
	try:
		vector = (await model.embed([text]))[0]
	except Exception:
		logger.exception("embedding call failed", extra=extra)
		raise
	logger.info(
		"embedding call completed",
		extra={
			**extra,
			"duration_ms": round((time.perf_counter() - started) * 1000, 2),
			"dimension": len(vector),
		},
	)
	return vector


async def embed_texts(
	texts: list[str],
	session: AsyncSession,
	batch_size: int | None = None,
	parallel: bool = True,
) -> list[list[float]]:
	"""embed a list of texts in batches. preserves input order.

	batch_size defaults to settings.assets.embeddings.batch_size when not set.
	parallel=True (default): all batches are gathered concurrently.
	parallel=False: sequential - useful for rate-limited or ordered paths.
	"""
	if not texts:
		return []
	model = await _get_embedding_model(session)
	actual_batch = batch_size or settings.assets.embeddings.batch_size
	batches = [texts[i : i + actual_batch] for i in range(0, len(texts), actual_batch)]
	extra: dict[str, object] = {
		"model": model.model_name,
		"text_count": len(texts),
		"batch_count": len(batches),
		"batch_size": actual_batch,
		"parallel": parallel,
		"input_chars": sum(len(text) for text in texts),
	}
	started = time.perf_counter()
	logger.info("embedding batch started", extra=extra)
	try:
		if parallel:
			nested = await asyncio.gather(*(model.embed(b) for b in batches))
			vectors = [vec for batch in nested for vec in batch]
		else:
			vectors = []
			for batch in batches:
				vectors.extend(await model.embed(batch))
	except Exception:
		logger.exception("embedding batch failed", extra=extra)
		raise
	logger.info(
		"embedding batch completed",
		extra={
			**extra,
			"duration_ms": round((time.perf_counter() - started) * 1000, 2),
			"dimension": len(vectors[0]) if vectors else 0,
		},
	)
	return vectors


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
