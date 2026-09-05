"""base contextualized embedding adapter - capability ABC."""

from abc import ABC, abstractmethod

from .embeddings import BaseEmbeddingAdapter, EmbeddingInputType


class BaseContextualizedEmbeddingAdapter(BaseEmbeddingAdapter, ABC):
	"""capability ABC for contextualized embedding APIs.

	adapters implementing this interface provide:
	- embed(): standalone texts (queries, single-chunk documents)
	- embed_contextualized(): a document's chunks embedded in one call,
		so every chunk vector carries whole-document context
	"""

	@abstractmethod
	async def embed_contextualized(
		self,
		documents: list[list[str]],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[list[float]]]:
		"""embed chunked documents with whole-document context.

		args:
			documents: one list of chunk texts per document
			model: provider model identifier
			input_type: retrieval role of the texts

		returns:
			per document, one embedding vector per chunk
		"""
		...
