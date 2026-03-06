"""EmbeddingModel high-level interface - unified access to embedding models."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import ConfigDict, Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
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
		*,
		adapter: EmbeddingsAdapter | dict[str, Any],
		**fields: Any,
	) -> EmbeddingModel:
		"""Create an embedding model with explicit adapter configuration."""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

	async def embed(self, texts: list[str]) -> list[list[float]]:
		"""generate embeddings for the given texts."""
		return await self.adapter.embed(texts, model=self.model_name)
