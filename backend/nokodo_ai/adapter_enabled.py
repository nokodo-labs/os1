"""shared adapter-enabled model behavior."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from pydantic import ConfigDict, Field, model_validator

from .adapters.base.adapter import BaseAdapter
from .base import Base


def split_model_identifier(
	model: str,
	*,
	default_provider: str = "openai",
) -> tuple[str, str | None, str]:
	"""split a model identifier into (provider, variant, model_name)."""
	if ":" in model:
		provider_part, model_name = model.split(":", 1)
	else:
		provider_part = default_provider
		model_name = model

	if "." in provider_part:
		provider, variant = provider_part.split(".", 1)
	else:
		provider = provider_part
		variant = None

	return provider, variant, model_name


class AdapterEnabledBase[AdapterType: BaseAdapter](Base):
	"""base model for interfaces that resolve an adapter."""

	_adapter_resolver: ClassVar[Callable[[str, str | None], str | None]]

	provider: str | None = Field(default=None, description="resolved provider name")
	variant: str | None = Field(default=None, description="resolved adapter variant")
	model_name: str = Field(..., description="resolved model name")

	adapter: AdapterType = Field(
		description="resolved adapter instance",
	)

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	async def __aenter__(self) -> AdapterEnabledBase[AdapterType]:
		return self

	async def __aexit__(self, exc_type, exc_value, traceback) -> None:
		await self.close()

	def __init__(self, model: str | None = None, **data: Any) -> None:
		# convenience: allow `X("provider:model")` / `X("model")`
		if model is not None:
			data["model_name"] = model
		super().__init__(**data)

	@model_validator(mode="before")
	@classmethod
	def _resolve_adapter_enabled_config(cls, data: Any) -> Any:
		"""normalize adapter-enabled input dictionaries.

		intended to be used from pydantic `mode="before"` validators.
		"""
		if not isinstance(data, dict):
			return data

		# legacy convenience: accept `model` as an alias for `model_name`
		if "model_name" not in data and "model" in data:
			model_value = data.pop("model")
			if isinstance(model_value, str) and model_value != "":
				data["model_name"] = model_value

		model_value = data.get("model_name")
		if isinstance(model_value, str) and model_value != "":
			# explicit format: provider[.variant]:model
			if ":" in model_value:
				provider, variant, name = split_model_identifier(model_value)
				data.setdefault("provider", provider)
				data.setdefault("variant", variant)
				data["model_name"] = name
			# implicit format: try to treat as provider first (vectorstores),
			# otherwise fall back to openai (chat/embeddings).
			elif "provider" not in data:
				candidate_provider = model_value
				adapter_type = cls._adapter_resolver(candidate_provider, None)
				if adapter_type is None:
					data["provider"] = "openai"
				else:
					data["provider"] = candidate_provider

		adapter = data.get("adapter")
		if isinstance(adapter, dict):
			type_value = adapter.get("type")
			if isinstance(type_value, str) and type_value != "":
				# allow shorthand `{"type": "openai"}` and infer provider
				if "." not in type_value:
					provider_value = data.get("provider")
					provider = (
						provider_value
						if isinstance(provider_value, str)
						else type_value
					)
					variant_value = data.get("variant")
					variant = variant_value if isinstance(variant_value, str) else None
					adapter_type = cls._adapter_resolver(provider, variant)
					if adapter_type is None:
						raise ValueError(f"unknown provider: {provider}")
					adapter["type"] = adapter_type
					data.setdefault("provider", provider)
				# if already fully qualified, infer provider from it if missing
				elif "provider" not in data:
					data["provider"] = type_value.split(".", 1)[0]

		if "adapter" not in data:
			provider_value = data.get("provider")
			provider = provider_value if isinstance(provider_value, str) else None
			variant_value = data.get("variant")
			variant = variant_value if isinstance(variant_value, str) else None

			if provider:
				adapter_type = cls._adapter_resolver(provider, variant)
				if adapter_type is None:
					raise ValueError(f"unknown provider: {provider}")
				data["adapter"] = {"type": adapter_type}

		return data

	async def close(self) -> None:
		"""close resources held by the adapter."""
		await self.adapter.close()
