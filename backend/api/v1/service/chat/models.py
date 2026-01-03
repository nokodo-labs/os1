"""model building and resolution for chat and embedding models."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.config import settings
from api.models.agent import Agent
from api.models.model import Model, ModelType
from api.models.provider import Provider
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.security import decrypt_string
from nokodo_ai.utils.typeid import TypeID


def _parse_adapter_type(adapter_type: str) -> tuple[str, str | None]:
	"""parse provider adapter type into (provider_key, api) tuple."""
	adapter_type = adapter_type.strip()
	if adapter_type == "":
		raise ValueError("provider adapter_type is empty")
	if "." not in adapter_type:
		return adapter_type, None
	provider, api = adapter_type.split(".", 1)
	provider = provider.strip()
	api = api.strip()
	return provider, api or None


def build_sdk_adapter_config(provider: Provider) -> dict[str, object]:
	"""build a fully explicit sdk adapter config dict from an orm Provider."""
	adapter_config: dict[str, object] = {
		"type": provider.adapter_type,
	}
	if provider.base_url is not None and provider.base_url.strip() != "":
		adapter_config["base_url"] = provider.base_url
	if provider.encrypted_api_key is not None and provider.encrypted_api_key != "":
		adapter_config["api_key"] = decrypt_string(
			provider.encrypted_api_key, settings.SECRET_KEY
		)
	return adapter_config


def build_chat_model(
	model: Model,
	*,
	temperature: float | None = None,
	max_tokens: int | None = None,
) -> ChatModel:
	"""create an sdk ChatModel with fully explicit adapter configuration.

	args:
		model: orm Model instance with provider relationship loaded
		temperature: optional temperature override
		max_tokens: optional max_tokens override

	returns:
		configured ChatModel ready for use
	"""
	provider_key, api = _parse_adapter_type(model.provider.adapter_type)
	adapter_config = build_sdk_adapter_config(model.provider)
	return ChatModel.model_validate(
		{
			"provider": provider_key,
			"api": api,
			"model_name": model.name,
			"adapter": adapter_config,
			"temperature": temperature,
			"max_tokens": max_tokens,
		}
	)


def build_embedding_model(model: Model) -> EmbeddingModel:
	"""create an sdk EmbeddingModel with fully explicit adapter configuration.

	args:
		model: orm Model instance with provider relationship loaded

	returns:
		configured EmbeddingModel ready for use
	"""
	if model.model_type != ModelType.EMBEDDING:
		raise ValueError(f"model {model.id} is not an embedding model")

	provider_key, api = _parse_adapter_type(model.provider.adapter_type)
	adapter_config = build_sdk_adapter_config(model.provider)
	return EmbeddingModel.model_validate(
		{
			"provider": provider_key,
			"api": api,
			"model_name": model.name,
			"adapter": adapter_config,
		}
	)


async def resolve_model_for_run(
	session: AsyncSession,
	*,
	agent_id: TypeID | None = None,
	model_id: TypeID | None = None,
	model: str | None = None,
) -> Model:
	"""resolve the orm Model for a run.

	resolution order:
	- agent_id -> agent.model
	- model_id -> Model
	- model (string) treated as Model id
	"""
	if agent_id is not None:
		stmt = (
			select(Agent)
			.options(selectinload(Agent.model).selectinload(Model.provider))
			.where(Agent.id == agent_id)
		)
		result = await session.execute(stmt)
		agent = result.scalars().one_or_none()
		if agent is None:
			raise HTTPException(status_code=404, detail="agent not found")
		if agent.model is None:
			raise HTTPException(status_code=409, detail="agent has no model configured")
		return agent.model

	if model_id is not None:
		stmt = (
			select(Model)
			.options(selectinload(Model.provider))
			.where(Model.id == model_id)
		)
		result = await session.execute(stmt)
		resolved_model = result.scalars().one_or_none()
		if resolved_model is None:
			raise HTTPException(status_code=404, detail="model not found")
		return resolved_model

	if model is not None and model.strip() != "":
		try:
			model_typeid = TypeID(model)
		except Exception as e:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="model must be a model id",
			) from e
		stmt = (
			select(Model)
			.options(selectinload(Model.provider))
			.where(Model.id == model_typeid)
		)
		result = await session.execute(stmt)
		resolved_model = result.scalars().one_or_none()
		if resolved_model is None:
			raise HTTPException(status_code=404, detail="model not found")
		return resolved_model

	raise HTTPException(
		status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
		detail="agent_id, model_id, or model is required",
	)


async def resolve_chat_model_for_run(
	session: AsyncSession,
	*,
	agent_id: TypeID | None = None,
	model_id: TypeID | None = None,
	model: str | None = None,
	temperature: float | None = None,
	max_tokens: int | None = None,
) -> ChatModel:
	"""resolve and build an sdk ChatModel with full adapter config."""
	resolved_model = await resolve_model_for_run(
		session,
		agent_id=agent_id,
		model_id=model_id,
		model=model,
	)
	return build_chat_model(
		resolved_model,
		temperature=temperature,
		max_tokens=max_tokens,
	)


async def resolve_embedding_model(
	session: AsyncSession,
	model_id: TypeID,
) -> EmbeddingModel:
	"""resolve and build an sdk EmbeddingModel from a model id.

	args:
		session: database session
		model_id: id of the embedding model

	returns:
		configured EmbeddingModel ready for use
	"""
	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if model is None:
		raise HTTPException(status_code=404, detail="model not found")
	return build_embedding_model(model)
