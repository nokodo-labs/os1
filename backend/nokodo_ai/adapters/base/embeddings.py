"""base embedding adapter - capability ABC for embedding models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from .adapter import BaseAdapter


EmbeddingInputType = Literal["query", "document"]
"""retrieval role of the text being embedded"""


class BaseEmbeddingAdapter(BaseAdapter, ABC):
	"""capability ABC for embedding APIs.

	adapters implementing this interface provide:
	- embed(): convert text to vector embeddings
	"""

	@abstractmethod
	async def embed(
		self,
		texts: list[str],
		model: str,
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		"""generate embeddings for the given texts.

		args:
			texts: list of strings to embed
			model: provider model identifier
			input_type: retrieval role of the texts. adapters whose provider
				supports asymmetric embeddings use it; the rest ignore it.

		returns:
			list of embedding vectors (one per input text)
		"""
		...

	def count_tokens(self, texts: list[str], model: str) -> list[int] | None:
		"""exact token count per text, or None when no tokenizer is available.

		optional capability. adapters whose provider exposes a public
		tokenizer override this; the rest fall back to estimation upstream.
		"""
		_ = (texts, model)
		return None
