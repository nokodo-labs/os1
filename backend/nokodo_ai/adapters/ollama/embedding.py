"""ollama embedding adapter."""

from __future__ import annotations

from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter


class OllamaEmbeddingAdapter(BaseOllamaAdapter, BaseEmbeddingAdapter):
	"""adapter for ollama's embedding API."""

	def __init__(
		self,
		*,
		model: str = "nomic-embed-text",
		base_url: str = "http://localhost:11434",
		timeout: float = 60.0,
	) -> None:
		"""initialize ollama embedding adapter.

		args:
			model: embedding model name
			base_url: ollama server URL
			timeout: request timeout in seconds
		"""
		super().__init__(base_url=base_url, timeout=timeout)
		self.model = model

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings using ollama's embedding API."""
		raise NotImplementedError("ollama embedding adapter not yet implemented")
