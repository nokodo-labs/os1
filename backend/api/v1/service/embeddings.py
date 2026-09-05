"""embedding model building and resolution for the api."""

import logging
import time
from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.models.model import Model, ModelType
from api.models.provider import Provider
from api.redis import on_invalidation
from api.runtime import on_settings_reload
from api.schemas.common import MISSING, MissingType
from api.settings import settings
from nokodo_ai.embeddings import (
	ContextualizedEmbeddingModel,
	EmbeddingInputType,
	EmbeddingModel,
)
from nokodo_ai.utils.concurrency import gather_bounded
from nokodo_ai.utils.tokens import estimate_tokens
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

_cached_embedding_model: EmbeddingModel | ContextualizedEmbeddingModel | None = None
"""process-level cache of the active embedding model, resolved once per process."""

_cached_embedding_input_limit: int | None | MissingType = MISSING
"""per-call token capacity of the cached model. None declares unlimited
(contextualized models); MISSING means not resolved yet."""

MAX_BATCH_TEXTS = 1000
"""hard cap on texts per embedding request; strictest common provider limit."""


def reset_embedding_model_cache() -> None:
	"""invalidate the cached embedding model (e.g. after settings change)."""
	global _cached_embedding_model, _cached_embedding_input_limit
	_cached_embedding_model = None
	_cached_embedding_input_limit = MISSING


# self-register: cleared on model/provider entity changes and after every
# settings snapshot reload.
on_invalidation("embedding_model", reset_embedding_model_cache)
on_settings_reload(reset_embedding_model_cache)


async def _get_embedding_model(
	session: AsyncSession | None = None,
) -> EmbeddingModel | ContextualizedEmbeddingModel:
	"""return the cached embedding model, resolving from DB on first call.

	when session is None and the cache is cold, opens its own short-lived
	session for the DB lookup. callers in long-running task code should pass
	None after warming the cache in an earlier phase so no connection is held
	during external I/O.
	"""
	global _cached_embedding_model
	if _cached_embedding_model is not None:
		return _cached_embedding_model
	if session is None:
		async with async_session_local() as owned:
			return await _get_embedding_model(owned)
	model = await resolve_embedding_model(session)
	contextualized = model.model_type == ModelType.CONTEXTUALIZED_EMBEDDING
	if not contextualized and (
		model.context_window is None or model.context_window <= 0
	):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"embedding model {model.name} has no context_window configured",
		)
	built = build_embedding_model(model)
	global _cached_embedding_input_limit
	_cached_embedding_input_limit = None if contextualized else model.context_window
	_cached_embedding_model = built
	logger.info(
		"cached embedding model: %s (provider=%s)",
		model.name,
		model.provider.name,
	)
	return built


async def embedding_token_capacity(session: AsyncSession | None = None) -> int | None:
	"""return how many tokens one embedding call accepts; None means unlimited.

	this is the routing metric for the vectorization architecture: None
	(contextualized embedding models) never splits; a finite capacity (the
	model's required context_window) splits text before embedding. resolves
	and caches the model on first call, erroring when the active embedding
	model has no context_window.
	"""
	await _get_embedding_model(session)
	capacity = _cached_embedding_input_limit
	if capacity is None or isinstance(capacity, int):
		return capacity
	raise HTTPException(
		status_code=status.HTTP_409_CONFLICT,
		detail="embedding model capacity is unresolved",
	)


async def count_input_tokens(
	texts: list[str],
	session: AsyncSession | None = None,
) -> list[int] | None:
	"""exact token counts per text, or None when the adapter has no tokenizer."""
	model = await _get_embedding_model(session)
	return model.count_tokens(texts)


async def embed_text(
	text: str,
	session: AsyncSession | None = None,
	input_type: EmbeddingInputType = "query",
) -> list[float]:
	"""embed a single text string. defaults to the query retrieval role."""
	model = await _get_embedding_model(session)
	extra: dict[str, object] = {
		"model": model.model_name,
		"text_count": 1,
		"input_chars": len(text),
	}
	started = time.perf_counter()
	logger.info("embedding call started", extra=extra)
	try:
		vector = (await model.embed([text], input_type=input_type))[0]
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


def _pack_batches(
	texts: list[str],
	counts: list[int],
	token_budget: int,
) -> list[list[str]]:
	"""greedily pack texts, in order, into batches under the request token budget."""
	batches: list[list[str]] = []
	current: list[str] = []
	current_tokens = 0
	for text, tokens in zip(texts, counts):
		if current and (
			current_tokens + tokens > token_budget or len(current) >= MAX_BATCH_TEXTS
		):
			batches.append(current)
			current = []
			current_tokens = 0
		current.append(text)
		current_tokens += tokens
	if current:
		batches.append(current)
	return batches


async def embed_texts(
	texts: list[str],
	session: AsyncSession | None = None,
	parallel: bool = True,
	max_concurrency: int | None = None,
	input_type: EmbeddingInputType = "document",
) -> list[list[float]]:
	"""embed a list of texts in token-budget-packed batches. preserves input order.

	defaults to the document retrieval role (this is the bulk indexing path).
	each request packs texts up to settings.assets.embeddings.batch_token_budget
	tokens (exact counts when the adapter has a tokenizer, estimates otherwise)
	and at most MAX_BATCH_TEXTS texts.
	parallel=True (default): batches are embedded concurrently, capped by
	max_concurrency.
	parallel=False: sequential - useful for rate-limited or ordered paths.

	max_concurrency caps how many batches embed at once when parallel. it
	defaults to settings.assets.embeddings.max_concurrency (100); set that
	setting to null for fully unbounded fan-out.
	"""
	if not texts:
		return []
	model = await _get_embedding_model(session)
	counts = model.count_tokens(texts) or [estimate_tokens(text) for text in texts]
	token_budget = settings.assets.embeddings.batch_token_budget
	actual_concurrency = (
		max_concurrency
		if max_concurrency is not None
		else settings.assets.embeddings.max_concurrency
	)
	batches = _pack_batches(texts, counts, token_budget)
	extra: dict[str, object] = {
		"model": model.model_name,
		"text_count": len(texts),
		"batch_count": len(batches),
		"token_budget": token_budget,
		"parallel": parallel,
		"max_concurrency": actual_concurrency,
		"input_chars": sum(len(text) for text in texts),
	}
	started = time.perf_counter()
	logger.info("embedding batch started", extra=extra)
	try:
		if parallel:
			nested = await gather_bounded(
				(model.embed(b, input_type=input_type) for b in batches),
				limit=actual_concurrency,
			)
			vectors = [vec for batch in nested for vec in batch]
		else:
			vectors = []
			for batch in batches:
				vectors.extend(await model.embed(batch, input_type=input_type))
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


def build_embedding_model(
	model: Model,
) -> EmbeddingModel | ContextualizedEmbeddingModel:
	"""create an SDK embedding model from an ORM model, keyed by its model type."""
	if model.model_type not in (
		ModelType.EMBEDDING,
		ModelType.CONTEXTUALIZED_EMBEDDING,
	):
		raise ValueError(f"model {model.id} is not an embedding model")

	adapter_type = model.provider.adapter_type
	if model.adapter is not None:
		adapter_type += f".{model.adapter}"

	adapter_config = build_sdk_adapter_config(model.provider, adapter_type=adapter_type)
	if model.model_type == ModelType.CONTEXTUALIZED_EMBEDDING:
		return ContextualizedEmbeddingModel.create(model.name, adapter=adapter_config)
	return EmbeddingModel.create(model.name, adapter=adapter_config)


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
		.where(
			Model.model_type.in_(
				(ModelType.EMBEDDING, ModelType.CONTEXTUALIZED_EMBEDDING)
			)
		)
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
