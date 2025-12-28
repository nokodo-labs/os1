"""ollama embedding adapter."""

from __future__ import annotations

from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter


class OllamaEmbeddingAdapter(BaseOllamaAdapter, BaseEmbeddingAdapter):
	"""adapter for ollama's embedding API."""

	async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
		"""generate embeddings using ollama's embedding API."""
		raise NotImplementedError("ollama embedding adapter not yet implemented")
