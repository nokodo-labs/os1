"""base embedding adapter - capability ABC for embedding models."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseEmbeddingAdapter(ABC):
	"""capability ABC for embedding APIs.

	adapters implementing this interface provide:
	- embed(): convert text to vector embeddings
	"""

	@abstractmethod
	async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
		"""generate embeddings for the given texts.

		args:
			texts: list of strings to embed

		returns:
			list of embedding vectors (one per input text)
		"""
		...
