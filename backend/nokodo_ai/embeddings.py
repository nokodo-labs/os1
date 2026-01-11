"""EmbeddingModel high-level interface - unified access to embedding models."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, model_validator

from .adapter_enabled import AdapterEnabledMixin, split_model_identifier
from .adapters.embeddings import (
	EmbeddingAdapter,
	resolve_embedding_adapter,
)


class EmbeddingModel(AdapterEnabledMixin[EmbeddingAdapter]):
	"""high-level unified interface for embedding models.

	usage (magic - auto-selects adapter):
		embedder = EmbeddingModel("openai:text-embedding-3-large")
		vectors = await embedder.embed(["hello", "world"])

	usage (explicit adapter):
		from nokodo_ai.adapters.openai.embedding import OpenAIEmbeddingAdapter
		adapter = OpenAIEmbeddingAdapter(api_key="...")
		embedder = EmbeddingModel(
			model="openai:text-embedding-3-large",
			adapter=adapter,
		)
	"""

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	def __init__(self, model: str | None = None, **data: Any) -> None:
		if model is not None:
			data["model"] = model
		super().__init__(**data)

	@model_validator(mode="before")
	@classmethod
	def resolve_adapter_config(cls, data: Any) -> Any:
		"""resolve adapter configuration from input data."""
		if isinstance(data, dict):
			model = data.pop("model", None)
			if model and isinstance(model, str):
				provider, variant, name = split_model_identifier(model)
				data.setdefault("provider", provider)
				data.setdefault("variant", variant)
				data.setdefault("model_name", name)

			if "adapter" not in data:
				provider = data.get("provider")
				variant = data.get("variant")

				if provider:
					adapter_type = resolve_embedding_adapter(provider, variant)
					if not adapter_type:
						raise ValueError(f"unknown embedding provider: {provider}")
					adapter_config = {"type": adapter_type}
					data["adapter"] = adapter_config

		return data

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings for the given texts."""
		return await self.adapter.embed(texts, model=self.model_name)
