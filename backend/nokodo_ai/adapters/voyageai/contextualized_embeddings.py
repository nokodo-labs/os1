"""voyageai contextualized embedding adapter."""

from typing import Any, Literal

from ..base.contextualized_embeddings import BaseContextualizedEmbeddingAdapter
from ..base.embeddings import EmbeddingInputType
from .base import BaseVoyageAIAdapter


class VoyageAIContextualizedEmbeddingsAdapter(
	BaseVoyageAIAdapter,
	BaseContextualizedEmbeddingAdapter,
):
	"""adapter for voyageai's contextualized chunk embedding API."""

	type: Literal["voyageai.contextualized_embedding"] = (
		"voyageai.contextualized_embedding"
	)

	async def embed(
		self,
		texts: list[str],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		"""embed standalone texts as single-chunk documents."""
		nested = await self.embed_contextualized(
			[[text] for text in texts],
			model,
			input_type,
		)
		return [chunks[0] for chunks in nested]

	async def embed_contextualized(
		self,
		documents: list[list[str]],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[list[float]]]:
		kwargs: dict[str, Any] = {}
		if input_type is not None:
			kwargs["input_type"] = input_type
		result = await self._client.contextualized_embed(
			inputs=documents,
			model=model,
			**kwargs,
		)
		# float() per value: quantized output_dtype modes return ints; we never
		# request quantization, so the values are always floats.
		return [
			[[float(v) for v in embedding] for embedding in r.embeddings]
			for r in result.results
		]

	def count_tokens(self, texts: list[str], model: str) -> list[int]:
		"""per-text token counts via voyageai tokenizer."""
		tokenized = self._client.tokenize(texts, model)
		return [len(t.tokens) for t in tokenized]
