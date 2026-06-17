"""voyageai embedding adapter."""

from __future__ import annotations

from typing import Any, Literal

from ..base.embeddings import BaseEmbeddingAdapter, EmbeddingInputType
from .base import BaseVoyageAIAdapter


class VoyageAIEmbeddingsAdapter(BaseVoyageAIAdapter, BaseEmbeddingAdapter):
	"""adapter for voyageai's embedding API."""

	type: Literal["voyageai.embedding"] = "voyageai.embedding"

	async def embed(
		self,
		texts: list[str],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		kwargs: dict[str, Any] = {}
		if input_type is not None:
			kwargs["input_type"] = input_type

		result = await self._client.embed(texts, model=model, **kwargs)
		# voyageai exposes embeddings as list[list[float]] | list[list[int]]
		# because quantized output_dtype modes return ints. we never request
		# quantization, so the values are always floats. explicit float()
		# call satisfies the type checker without a cast.
		return [[float(v) for v in e] for e in result.embeddings]

	def count_tokens(self, texts: list[str], model: str) -> list[int]:
		"""per-text token counts via voyageai tokenizer."""
		tokenized = self._client.tokenize(texts, model)
		return [len(t.tokens) for t in tokenized]
