"""Service layer for provider models."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import InputModality, Model
from api.models.provider import Provider, ProviderStatus
from api.schemas.model import ModelCreate, ModelUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission


logger = logging.getLogger(__name__)


def _default_input_modalities(model_type: str) -> list[str]:
	"""return the default input modalities for a model type."""
	match model_type:
		case "chat_model":
			return [InputModality.TEXT, InputModality.IMAGES]
		case "embedding":
			return [InputModality.TEXT]
		case "image_generation":
			return [InputModality.TEXT, InputModality.IMAGES]
		case "audio":
			return [InputModality.TEXT, InputModality.AUDIO]
		case "video":
			return [InputModality.TEXT, InputModality.IMAGES, InputModality.VIDEO]
		case _:
			return [InputModality.TEXT]


_DEFAULT_BASE_URLS: dict[str, str] = {
	"openai": "https://api.openai.com/v1",
	"anthropic": "https://api.anthropic.com/v1",
	"ollama": "http://localhost:11434/v1",
}


def _default_model_adapter(provider_key: str, model_type: str) -> str | None:
	"""return the default adapter variant for a given provider+model type."""
	provider_key = provider_key.strip()
	if provider_key == "":
		return None

	if model_type == "chat_model":
		match provider_key:
			case "openai":
				return "chat_completions"
			case "anthropic":
				return "messages"
			case "google":
				return "generate_content"
			case "ollama":
				return "chat"
	if model_type == "embedding":
		match provider_key:
			case "openai" | "ollama":
				return "embedding"
	return None


def _normalize_base_url(provider: Provider) -> str | None:
	if provider.base_url is not None and provider.base_url.strip() != "":
		return provider.base_url.strip().rstrip("/")
	default = _DEFAULT_BASE_URLS.get(provider.adapter_type)
	if default is None:
		return None
	return default.rstrip("/")


def _merge_headers(
	*,
	base: dict[str, str],
	additional: dict | None,
) -> dict[str, str]:
	headers = dict(base)
	if additional is None:
		return headers
	for key, value in additional.items():
		if isinstance(key, str) and isinstance(value, str) and key.strip() != "":
			headers[key] = value
	return headers


def _parse_openai_models_payload(payload: object) -> list[str]:
	if not isinstance(payload, dict):
		raise ValueError("invalid models payload")
	data = payload.get("data")
	if not isinstance(data, list):
		raise ValueError("invalid models payload")

	model_ids: list[str] = []
	for item in data:
		if not isinstance(item, dict):
			continue
		model_id = item.get("id")
		if isinstance(model_id, str) and model_id.strip() != "":
			model_ids.append(model_id)
	return model_ids


def _parse_anthropic_models_payload(
	payload: object,
) -> tuple[list[tuple[str, str | None]], str | None, bool]:
	if not isinstance(payload, dict):
		raise ValueError("invalid models payload")
	data = payload.get("data")
	if not isinstance(data, list):
		raise ValueError("invalid models payload")

	items: list[tuple[str, str | None]] = []
	for item in data:
		if not isinstance(item, dict):
			continue
		model_id = item.get("id")
		if not isinstance(model_id, str) or model_id.strip() == "":
			continue
		display_name = item.get("display_name")
		items.append(
			(model_id, display_name if isinstance(display_name, str) else None)
		)

	last_id = payload.get("last_id")
	has_more = payload.get("has_more")
	return (
		items,
		last_id if isinstance(last_id, str) and last_id.strip() != "" else None,
		has_more is True,
	)


async def _fetch_openai_compatible_models(
	client: httpx.AsyncClient,
	*,
	base_url: str,
	headers: dict[str, str],
) -> list[str]:
	resp = await client.get(f"{base_url}/models", headers=headers)
	resp.raise_for_status()
	payload = resp.json()
	return _parse_openai_models_payload(payload)


async def _fetch_anthropic_models(
	client: httpx.AsyncClient,
	*,
	base_url: str,
	headers: dict[str, str],
) -> list[tuple[str, str | None]]:
	all_items: list[tuple[str, str | None]] = []
	params: dict[str, str] | None = None
	while True:
		resp = await client.get(
			f"{base_url}/models",
			headers=headers,
			params=params,
		)
		resp.raise_for_status()
		payload = resp.json()
		items, last_id, has_more = _parse_anthropic_models_payload(payload)
		all_items.extend(items)
		if not has_more or last_id is None:
			return all_items
		params = {"after_id": last_id}


def _is_valid_autofetch_provider(provider: Provider) -> bool:
	if provider.status != ProviderStatus.ENABLED:
		return False
	if not provider.is_autofetch_enabled:
		return False
	return provider.adapter_type in _DEFAULT_BASE_URLS


def _namespaced_display_name(
	*,
	prefix: str | None,
	model_id: str,
	upstream_display_name: str | None,
) -> str | None:
	# display names are no longer prefixed - models are unique by
	# (name, provider_id) instead, so the prefix is unnecessary.
	return upstream_display_name


async def _sync_autofetched_models(
	session: AsyncSession,
	*,
	provider_id: str | None,
) -> None:
	stmt = select(Provider).where(
		Provider.status == ProviderStatus.ENABLED,
		Provider.is_autofetch_enabled.is_(True),
	)
	if provider_id is not None:
		stmt = stmt.where(Provider.id == provider_id)

	result = await session.execute(stmt)
	providers = list(result.scalars().all())
	providers = [p for p in providers if _is_valid_autofetch_provider(p)]
	if len(providers) == 0:
		return

	async with httpx.AsyncClient(timeout=15.0) as client:
		for provider in providers:
			base_url = _normalize_base_url(provider)
			if base_url is None:
				continue

			try:
				if provider.adapter_type == "anthropic":
					api_key = provider.api_key
					if api_key is None:
						continue
					headers = _merge_headers(
						base={
							"X-Api-Key": api_key,
							"anthropic-version": "2023-06-01",
						},
						additional=provider.additional_headers,
					)
					fetched = await _fetch_anthropic_models(
						client,
						base_url=base_url,
						headers=headers,
					)
					fetched_by_id = {model_id: display for model_id, display in fetched}
				else:
					base_headers: dict[str, str] = {}
					if provider.adapter_type == "openai":
						api_key = provider.api_key
						if api_key is None:
							continue
						base_headers["Authorization"] = f"Bearer {api_key}"
					headers = _merge_headers(
						base=base_headers,
						additional=provider.additional_headers,
					)
					model_ids = await _fetch_openai_compatible_models(
						client,
						base_url=base_url,
						headers=headers,
					)
					fetched_by_id = {model_id: None for model_id in model_ids}
			except (httpx.HTTPError, ValueError) as exc:
				logger.warning(
					"provider model autofetch failed",
					extra={
						"provider_id": provider.id,
						"provider_adapter": provider.adapter_type,
						"error": str(exc),
					},
				)
				continue

			result_models = await session.execute(
				select(Model).where(Model.provider_id == provider.id)
			)
			existing_models = list(result_models.scalars().all())
			existing_by_name = {m.name: m for m in existing_models}
			fetched_ids = set(fetched_by_id.keys())

			for model_id, upstream_display_name in fetched_by_id.items():
				existing = existing_by_name.get(model_id)
				if existing is not None and not existing.is_autofetched:
					continue

				display_name = _namespaced_display_name(
					prefix=provider.model_prefix,
					model_id=model_id,
					upstream_display_name=upstream_display_name,
				)

				if existing is None:
					session.add(
						Model(
							provider_id=provider.id,
							name=model_id,
							display_name=display_name,
							adapter=_default_model_adapter(
								provider.adapter_type,
								"chat_model",
							),
							capabilities=[],
							enabled=True,
							is_autofetched=True,
						)
					)
					continue

				existing.enabled = True
				existing.is_autofetched = True
				existing.display_name = display_name
				if existing.adapter is None:
					existing.adapter = _default_model_adapter(
						provider.adapter_type,
						"chat_model",
					)

			for model in existing_models:
				if not model.is_autofetched:
					continue
				if model.name not in fetched_ids:
					await session.delete(model)

			provider.last_synced_at = datetime.now(UTC)
			session.add(provider)

	await session.commit()


async def _ensure_provider(
	provider_id: str,
	session: AsyncSession,
	principal: Principal,
) -> None:
	require_permission(principal, "models:manage")
	provider = await session.get(Provider, provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)


async def _get_model(
	model_id: str,
	session: AsyncSession,
	principal: Principal,
) -> Model:
	require_permission(principal, "models:manage")
	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)
	return model


def _check_valid_adapter(
	provider_type: str,
	model_type: str,
	adapter: str | None,
) -> None:
	if adapter is None:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="adapter cannot be null.",
		)

	valid = False
	if model_type == "chat_model":
		if provider_type == "openai":
			valid = adapter in ("chat_completions", "responses")
		elif provider_type == "anthropic":
			valid = adapter == "messages"
		elif provider_type == "google":
			valid = adapter == "generate_content"
		elif provider_type == "ollama":
			valid = adapter == "chat"
	elif model_type == "embedding":
		if provider_type in ("openai", "ollama"):
			valid = adapter == "embedding"

	if not valid:
		display_model_type = "chat model" if model_type == "chat_model" else model_type
		msg = (
			f"Invalid adapter '{adapter}' for provider type '{provider_type}' "
			f"and model type '{display_model_type}'."
		)
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=msg,
		)


async def create_model(
	model_in: ModelCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Model:
	require_permission(principal, "models:manage")

	provider = await session.get(Provider, model_in.provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)

	data = model_in.model_dump(by_alias=True)
	model_type = str(data.get("model_type") or "chat_model")

	if data.get("adapter") is None:
		data["adapter"] = _default_model_adapter(provider.adapter_type, model_type)

	if not data.get("input_modalities"):
		data["input_modalities"] = _default_input_modalities(model_type)

	_check_valid_adapter(provider.adapter_type, model_type, data.get("adapter"))

	model = Model(**data)
	session.add(model)
	await session.commit()
	return await _get_model(str(model.id), session, principal)


async def list_models(
	session: AsyncSession,
	*,
	principal: Principal,
	provider_id: str | None = None,
) -> list[Model]:
	require_permission(principal, "models:manage")
	await _sync_autofetched_models(session, provider_id=provider_id)
	stmt = (
		select(Model)
		.options(selectinload(Model.provider))
		.order_by(Model.created_at.desc())
	)

	if provider_id:
		stmt = stmt.where(Model.provider_id == provider_id)

	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_model(
	model_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Model:
	return await _get_model(model_id, session, principal)


async def update_model(
	model_id: str,
	model_in: ModelUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Model:
	model = await _get_model(model_id, session, principal)

	update_data = model_in.model_dump(exclude_unset=True)

	if "adapter" in update_data or "model_type" in update_data:
		adapter = update_data.get("adapter", model.adapter)
		model_type = str(update_data.get("model_type", model.model_type))
		_check_valid_adapter(model.provider.adapter_type, model_type, adapter)

	for field, value in update_data.items():
		setattr(model, field, value)

	await session.commit()
	return await _get_model(model_id, session, principal)


async def delete_model(
	model_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	model = await _get_model(model_id, session, principal)
	await session.delete(model)
	await session.commit()
