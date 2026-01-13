"""EmbeddingModel high-level interface - unified access to embedding models."""

from __future__ import annotations

from pydantic import ConfigDict

from .adapter_enabled import AdapterEnabledBase
from .adapters.embeddings import (
	EmbeddingsAdapter,
	resolve_embeddings_adapter,
)


class EmbeddingModel(AdapterEnabledBase[EmbeddingsAdapter]):
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

	_adapter_resolver: ... = resolve_embeddings_adapter

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings for the given texts."""
		return await self.adapter.embed(texts, model=self.model_name)
