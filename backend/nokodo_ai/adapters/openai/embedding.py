"""openai embedding adapter."""

from __future__ import annotations

from typing import Literal

from ..base.embedding import BaseEmbeddingAdapter
from .base import BaseOpenAIAdapter


class OpenAIEmbeddingAdapter(BaseOpenAIAdapter, BaseEmbeddingAdapter):
	"""adapter for openai's embedding API."""

	type: Literal["openai.embedding"] = "openai.embedding"

	async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
		"""generate embeddings using openai's embedding API."""
		response = await self._client.embeddings.create(
			model=model,
			input=texts,
		)
		return [item.embedding for item in response.data]
