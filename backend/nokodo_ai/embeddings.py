"""EmbeddingModel high-level interface - unified access to embedding models."""

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.embeddings import EmbeddingInputType
from .adapters.contextualized_embeddings import (
	ContextualizedEmbeddingsAdapter,
	resolve_contextualized_embeddings_adapter,
)
from .adapters.embeddings import (
	EmbeddingsAdapter,
	resolve_embeddings_adapter,
)


class EmbeddingModel(AdapterEnabledBase[EmbeddingsAdapter]):
	"""high-level unified interface for embedding models.

	usage:
		embedder = EmbeddingModel.create(
			"text-embedding-3-large",
			adapter={"type": "openai", "api_key": "..."},
		)
		vectors = await embedder.embed(["hello", "world"])
	"""

	model_name: str = Field(..., description="model identifier")

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_embeddings_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		adapter: EmbeddingsAdapter | dict[str, Any],
		**fields: Any,
	) -> EmbeddingModel:
		"""Create an embedding model with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	async def embed(
		self,
		texts: list[str],
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		"""generate embeddings for the given texts.

		input_type marks whether the texts are search queries or stored
		documents; adapters whose provider supports asymmetric embeddings
		use it, the rest ignore it.
		"""
		return await self.adapter.embed(
			texts, model=self.model_name, input_type=input_type
		)

	def count_tokens(self, texts: list[str]) -> list[int] | None:
		"""exact token counts per text, or None when the adapter lacks a tokenizer."""
		return self.adapter.count_tokens(texts, model=self.model_name)


class ContextualizedEmbeddingModel(AdapterEnabledBase[ContextualizedEmbeddingsAdapter]):
	"""high-level unified interface for contextualized embedding models.

	embeds each document's chunks in one call so every chunk vector carries
	whole-document context; standalone texts embed exactly like EmbeddingModel.
	"""

	model_name: str = Field(..., description="model identifier")

	model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

	_adapter_resolver: ClassVar[AdapterResolver] = (
		resolve_contextualized_embeddings_adapter
	)

	@classmethod
	def create(
		cls,
		model_name: str,
		adapter: ContextualizedEmbeddingsAdapter | dict[str, Any],
		**fields: Any,
	) -> ContextualizedEmbeddingModel:
		"""Create a contextualized embedding model with an explicit adapter."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	async def embed(
		self,
		texts: list[str],
		input_type: EmbeddingInputType | None = None,
	) -> list[list[float]]:
		"""embed standalone texts (queries or single-chunk documents)."""
		return await self.adapter.embed(
			texts, model=self.model_name, input_type=input_type
		)

	async def embed_contextualized(
		self,
		documents: list[list[str]],
		input_type: EmbeddingInputType | None = None,
	) -> list[list[list[float]]]:
		"""embed chunked documents; returns one embedding per chunk per document."""
		return await self.adapter.embed_contextualized(
			documents, model=self.model_name, input_type=input_type
		)

	def count_tokens(self, texts: list[str]) -> list[int] | None:
		"""exact token counts per text, or None when the adapter lacks a tokenizer."""
		return self.adapter.count_tokens(texts, model=self.model_name)
