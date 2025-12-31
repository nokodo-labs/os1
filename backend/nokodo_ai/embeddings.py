"""EmbeddingModel high-level interface - unified access to embedding models."""

from __future__ import annotations

from pydantic import ConfigDict

from nokodo_ai.adapter_enabled import AdapterEnabledMixin, split_model_identifier
from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter


DEFAULT_PROVIDER = "openai"


class EmbeddingModel(AdapterEnabledMixin[BaseEmbeddingAdapter]):
	"""high-level unified interface for embedding models.

	usage (magic - auto-selects adapter):
		embedder = EmbeddingModel(model="openai:text-embedding-3-large")
		vectors = await embedder.embed(["hello", "world"])

	usage (explicit adapter):
		adapter = OpenAIEmbeddingAdapter(api_key="...")
		embedder = EmbeddingModel(
			model="openai:text-embedding-3-large",
			adapter=adapter,
		)
	"""

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	def _resolve_adapter_from_model(self, model: str) -> BaseEmbeddingAdapter:
		provider, variant, _model_name = split_model_identifier(
			model,
			default_provider=DEFAULT_PROVIDER,
		)

		match provider:
			case "openai":
				from nokodo_ai.adapters.openai import get_embedding_adapter

				return get_embedding_adapter(variant)

			case "ollama":
				from nokodo_ai.adapters.ollama import get_embedding_adapter

				return get_embedding_adapter(variant)

			case _:
				raise ValueError(f"unknown embedding provider: {provider}")

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings for the given texts."""
		_provider, _variant, model_name = split_model_identifier(
			self.model,
			default_provider=DEFAULT_PROVIDER,
		)
		return await self._adapter_resolved.embed(texts, model=model_name)
