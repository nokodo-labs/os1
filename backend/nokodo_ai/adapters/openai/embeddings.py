"""openai embedding adapter."""

from __future__ import annotations

from typing import Literal

import tiktoken

from ..base.embeddings import BaseEmbeddingAdapter, EmbeddingInputType
from .base import BaseOpenAIAdapter


class OpenAIEmbeddingsAdapter(BaseOpenAIAdapter, BaseEmbeddingAdapter):
	"""adapter for openai's embedding API."""

	type: Literal["openai.embedding"] = "openai.embedding"

	async def embed(
		self,
		texts: list[str],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		"""generate embeddings using openai's embedding API.

		openai has no asymmetric input_type, so it is ignored.
		"""
		_ = input_type
		response = await self._client.embeddings.create(
			model=model,
			input=texts,
		)
		return [item.embedding for item in response.data]

	def count_tokens(self, texts: list[str], model: str) -> list[int]:
		"""exact token counts via tiktoken; falls back to cl100k_base."""
		try:
			encoding = tiktoken.encoding_for_model(model)
		except KeyError:
			encoding = tiktoken.get_encoding("cl100k_base")
		return [len(encoding.encode(text)) for text in texts]
