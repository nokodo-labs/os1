"""openai embedding adapter."""

from __future__ import annotations

from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter


class OpenAIEmbeddingAdapter(BaseOpenAIAdapter, BaseEmbeddingAdapter):
	"""adapter for openai's embedding API."""

	def __init__(
		self,
		*,
		model: str = "text-embedding-3-large",
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize embedding adapter.

		args:
			model: embedding model identifier
			api_key: openai API key
			base_url: custom base URL
			timeout: request timeout in seconds
		"""
		super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)
		self.model = model

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings using openai's embedding API."""
		response = await self._client.embeddings.create(
			model=self.model,
			input=texts,
		)
		return [item.embedding for item in response.data]
