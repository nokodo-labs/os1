"""Service layer for provider models."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import InputModality, Model, ModelType
from api.models.provider import Provider, ProviderStatus
from api.schemas.model import ModelCreate, ModelUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission


logger = logging.getLogger(__name__)


# -- fetched model data -------------------------------------------------------


@dataclass
class FetchedModel:
	"""normalized model info returned by any provider's list-models endpoint."""

	id: str
	display_name: str | None = None
	model_type: ModelType = ModelType.CHAT_MODEL
	input_modalities: list[str] = field(default_factory=list)
	context_window: int | None = None
	input_cost: float | None = None
	output_cost: float | None = None


# -- defaults ------------------------------------------------------------------


def _default_input_modalities(model_type: str) -> list[str]:
	"""return the default input modalities for a model type."""
	match model_type:
		case "chat_model":
			return [InputModality.TEXT, InputModality.IMAGES]
		case "embedding":
			return [InputModality.TEXT]
		case "image":
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
	"google": "https://generativelanguage.googleapis.com/v1beta",
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
			case "openai" | "ollama" | "google":
				return "embedding"
	if model_type == "image":
		match provider_key:
			case "openai":
				return "images"
			case "google":
				return "predict_images"
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


# -- openai model type inference -----------------------------------------------


def _infer_openai_model_type(model_id: str) -> ModelType:
	"""best-effort model type inference from an openai model id."""
	lid = model_id.lower()
	if "embed" in lid:
		return ModelType.EMBEDDING
	if lid.startswith("dall-e") or lid.startswith("gpt-image"):
		return ModelType.IMAGE
	if lid.startswith("tts") or lid.startswith("whisper"):
		return ModelType.AUDIO
	return ModelType.CHAT_MODEL


def _infer_openai_modalities(model_id: str, model_type: ModelType) -> list[str]:
	"""best-effort input modality inference from an openai model id."""
	if model_type != ModelType.CHAT_MODEL:
		return _default_input_modalities(model_type.value)
	lid = model_id.lower()
	# audio models
	if "audio" in lid or lid.startswith("gpt-4o-audio"):
		return [InputModality.TEXT, InputModality.IMAGES, InputModality.AUDIO]
	# multimodal vision models
	vision_tags = ("gpt-4o", "gpt-4-turbo", "gpt-4.1", "o1", "o3", "o4")
	if any(tag in lid for tag in vision_tags):
		return [InputModality.TEXT, InputModality.IMAGES]
	return _default_input_modalities(model_type.value)


# -- openai parser -------------------------------------------------------------


def _parse_openai_models_payload(payload: object) -> list[FetchedModel]:
	"""parse the openai-compatible /v1/models response into FetchedModel list."""
	if not isinstance(payload, dict):
		raise ValueError("invalid models payload")
	data = payload.get("data")
	if not isinstance(data, list):
		raise ValueError("invalid models payload")

	results: list[FetchedModel] = []
	for item in data:
		if not isinstance(item, dict):
			continue
		model_id = item.get("id")
		if not isinstance(model_id, str) or model_id.strip() == "":
			continue
		model_type = _infer_openai_model_type(model_id)
		results.append(
			FetchedModel(
				id=model_id,
				display_name=None,
				model_type=model_type,
				input_modalities=_infer_openai_modalities(model_id, model_type),
			)
		)
	return results


# -- anthropic parser ----------------------------------------------------------


def _parse_anthropic_models_payload(
	payload: object,
) -> tuple[list[FetchedModel], str | None, bool]:
	if not isinstance(payload, dict):
		raise ValueError("invalid models payload")
	data = payload.get("data")
	if not isinstance(data, list):
		raise ValueError("invalid models payload")

	items: list[FetchedModel] = []
	for item in data:
		if not isinstance(item, dict):
			continue
		model_id = item.get("id")
		if not isinstance(model_id, str) or model_id.strip() == "":
			continue
		display_name = item.get("display_name")
		# all anthropic models are multimodal chat models
		items.append(
			FetchedModel(
				id=model_id,
				display_name=display_name if isinstance(display_name, str) else None,
				model_type=ModelType.CHAT_MODEL,
				input_modalities=[InputModality.TEXT, InputModality.IMAGES],
			)
		)

	last_id = payload.get("last_id")
	has_more = payload.get("has_more")
	return (
		items,
		last_id if isinstance(last_id, str) and last_id.strip() != "" else None,
		has_more is True,
	)


# -- google parser -------------------------------------------------------------


def _infer_google_model_type(
	methods: list[str],
	model_name: str,
) -> ModelType:
	"""infer model type from google supportedGenerationMethods."""
	if "embedContent" in methods:
		return ModelType.EMBEDDING
	if "predict" in methods:
		return ModelType.IMAGE
	lid = model_name.lower()
	if "imagen" in lid:
		return ModelType.IMAGE
	return ModelType.CHAT_MODEL


def _infer_google_modalities(model_type: ModelType) -> list[str]:
	if model_type == ModelType.EMBEDDING:
		return [InputModality.TEXT]
	if model_type == ModelType.IMAGE:
		return [InputModality.TEXT, InputModality.IMAGES]
	# gemini chat models accept text, images, audio, video
	return [
		InputModality.TEXT,
		InputModality.IMAGES,
		InputModality.AUDIO,
		InputModality.VIDEO,
	]


def _parse_google_models_payload(
	payload: object,
) -> tuple[list[FetchedModel], str | None]:
	"""parse the google generative language models response."""
	if not isinstance(payload, dict):
		raise ValueError("invalid models payload")
	models_list = payload.get("models")
	if not isinstance(models_list, list):
		raise ValueError("invalid models payload")

	results: list[FetchedModel] = []
	for item in models_list:
		if not isinstance(item, dict):
			continue
		full_name = item.get("name")
		if not isinstance(full_name, str) or full_name.strip() == "":
			continue
		# strip the "models/" prefix from google model names
		model_id = full_name.removeprefix("models/")

		display_name = item.get("displayName")
		methods = item.get("supportedGenerationMethods", [])
		if not isinstance(methods, list):
			methods = []

		model_type = _infer_google_model_type(methods, model_id)
		input_token_limit = item.get("inputTokenLimit")
		context_window = (
			int(input_token_limit)
			if isinstance(input_token_limit, (int, float))
			else None
		)

		results.append(
			FetchedModel(
				id=model_id,
				display_name=display_name if isinstance(display_name, str) else None,
				model_type=model_type,
				input_modalities=_infer_google_modalities(model_type),
				context_window=context_window,
			)
		)

	next_page_token = payload.get("nextPageToken")
	return (
		results,
		next_page_token
		if isinstance(next_page_token, str) and next_page_token.strip() != ""
		else None,
	)


# -- fetch functions -----------------------------------------------------------


async def _fetch_openai_compatible_models(
	client: httpx.AsyncClient,
	*,
	base_url: str,
	headers: dict[str, str],
) -> list[FetchedModel]:
	resp = await client.get(f"{base_url}/models", headers=headers)
	resp.raise_for_status()
	payload = resp.json()
	return _parse_openai_models_payload(payload)


async def _fetch_anthropic_models(
	client: httpx.AsyncClient,
	*,
	base_url: str,
	headers: dict[str, str],
) -> list[FetchedModel]:
	all_items: list[FetchedModel] = []
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


async def _fetch_google_models(
	client: httpx.AsyncClient,
	*,
	base_url: str,
	headers: dict[str, str],
) -> list[FetchedModel]:
	all_items: list[FetchedModel] = []
	params: dict[str, str] = {"pageSize": "100"}
	while True:
		resp = await client.get(
			f"{base_url}/models",
			headers=headers,
			params=params,
		)
		resp.raise_for_status()
		payload = resp.json()
		items, next_token = _parse_google_models_payload(payload)
		all_items.extend(items)
		if next_token is None:
			return all_items
		params["pageToken"] = next_token


# -- autofetch sync ------------------------------------------------------------


def _is_valid_autofetch_provider(provider: Provider) -> bool:
	if provider.status != ProviderStatus.ENABLED:
		return False
	if not provider.is_autofetch_enabled:
		return False
	return provider.adapter_type in _DEFAULT_BASE_URLS


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
				fetched = await _fetch_models_for_provider(client, provider, base_url)
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

			if fetched is None:
				continue

			fetched_by_id = {fm.id: fm for fm in fetched}

			result_models = await session.execute(
				select(Model).where(Model.provider_id == provider.id)
			)
			existing_models = list(result_models.scalars().all())
			existing_by_name = {m.name: m for m in existing_models}
			fetched_ids = set(fetched_by_id.keys())

			for fm in fetched:
				existing = existing_by_name.get(fm.id)
				if existing is not None and not existing.is_autofetched:
					continue

				adapter = _default_model_adapter(
					provider.adapter_type,
					fm.model_type.value,
				)
				modalities = fm.input_modalities or _default_input_modalities(
					fm.model_type.value,
				)

				if existing is None:
					session.add(
						Model(
							provider_id=provider.id,
							name=fm.id,
							display_name=fm.display_name,
							model_type=fm.model_type,
							adapter=adapter,
							input_modalities=modalities,
							context_window=fm.context_window,
							input_cost=fm.input_cost,
							output_cost=fm.output_cost,
							capabilities=[],
							enabled=True,
							is_autofetched=True,
						)
					)
					continue

				existing.enabled = True
				existing.is_autofetched = True
				existing.display_name = fm.display_name
				existing.input_modalities = modalities
				if existing.adapter is None:
					existing.adapter = adapter
				if fm.context_window is not None:
					existing.context_window = fm.context_window
				if fm.input_cost is not None:
					existing.input_cost = fm.input_cost
				if fm.output_cost is not None:
					existing.output_cost = fm.output_cost

			for model in existing_models:
				if not model.is_autofetched:
					continue
				if model.name not in fetched_ids:
					await session.delete(model)

			provider.last_synced_at = datetime.now(UTC)
			session.add(provider)

	await session.commit()


async def _fetch_models_for_provider(
	client: httpx.AsyncClient,
	provider: Provider,
	base_url: str,
) -> list[FetchedModel] | None:
	"""dispatch to the correct fetcher based on adapter_type."""
	if provider.adapter_type == "anthropic":
		api_key = provider.api_key
		if api_key is None:
			return None
		headers = _merge_headers(
			base={
				"X-Api-Key": api_key,
				"anthropic-version": "2023-06-01",
			},
			additional=provider.additional_headers,
		)
		return await _fetch_anthropic_models(client, base_url=base_url, headers=headers)

	if provider.adapter_type == "google":
		api_key = provider.api_key
		if api_key is None:
			return None
		headers = _merge_headers(
			base={},
			additional=provider.additional_headers,
		)
		# google uses query param for auth
		original_base = base_url
		base_url_with_key = f"{original_base}"
		# we pass key as a header via x-goog-api-key
		headers["x-goog-api-key"] = api_key
		return await _fetch_google_models(
			client, base_url=base_url_with_key, headers=headers
		)

	# openai-compatible (openai, ollama, custom)
	base_headers: dict[str, str] = {}
	api_key = provider.api_key
	if provider.adapter_type == "openai":
		if api_key is None:
			return None
		base_headers["Authorization"] = f"Bearer {api_key}"
	elif api_key is not None:
		base_headers["Authorization"] = f"Bearer {api_key}"
	headers = _merge_headers(
		base=base_headers,
		additional=provider.additional_headers,
	)
	return await _fetch_openai_compatible_models(
		client, base_url=base_url, headers=headers
	)


# -- CRUD helpers --------------------------------------------------------------


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
		if provider_type in ("openai", "ollama", "google"):
			valid = adapter == "embedding"
	elif model_type == "image":
		if provider_type == "openai":
			valid = adapter == "images"
		elif provider_type == "google":
			valid = adapter in ("predict_images", "generate_content_images")

	if not valid:
		_labels: dict[str, str] = {
			"chat_model": "chat model",
			"image": "image",
		}
		display_model_type = _labels.get(model_type, model_type)
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

	update_data = model_in.model_dump(exclude_unset=True, by_alias=True)

	if "adapter" in update_data or "model_type" in update_data:
		adapter = update_data.get("adapter", model.adapter)
		model_type = str(update_data.get("model_type", model.model_type))
		_check_valid_adapter(model.provider.adapter_type, model_type, adapter)

	for key, value in update_data.items():
		setattr(model, key, value)

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
