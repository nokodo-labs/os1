"""openai embedding adapter."""

from __future__ import annotations

from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter


class OpenAIEmbeddingAdapter(BaseOpenAIAdapter, BaseEmbeddingAdapter):
	"""adapter for openai's embedding API."""

	async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
		"""generate embeddings using openai's embedding API."""
		response = await self._client.embeddings.create(
			model=model,
			input=texts,
		)
		return [item.embedding for item in response.data]
