"""ollama embedding adapter."""

from __future__ import annotations

from typing import Literal

from ..base.embeddings import BaseEmbeddingAdapter
from .base import BaseOllamaAdapter


class OllamaEmbeddingsAdapter(BaseOllamaAdapter, BaseEmbeddingAdapter):
	"""adapter for ollama's embedding API."""

	type: Literal["ollama.embedding"] = "ollama.embedding"

	async def embed(self, texts: list[str], model: str) -> list[list[float]]:
		"""generate embeddings using ollama's embedding API."""
		_ = (texts, model)
		raise NotImplementedError("ollama embedding adapter not yet implemented")
