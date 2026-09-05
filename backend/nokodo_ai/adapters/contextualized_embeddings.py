"""contextualized embedding adapter union - the single entry point."""

from .base.contextualized_embeddings import BaseContextualizedEmbeddingAdapter
from .voyageai.contextualized_embeddings import (
	VoyageAIContextualizedEmbeddingsAdapter,
)


ContextualizedEmbeddingsAdapter = VoyageAIContextualizedEmbeddingsAdapter
"""union of contextualized embedding adapters; single member today."""


def resolve_contextualized_embeddings_adapter(
	provider: str,
	adapter: str | None,
) -> str | None:
	"""resolve the adapter type string from provider and api."""
	if provider == "voyageai":
		return "voyageai.contextualized_embedding"
	return None


__all__ = [
	"BaseContextualizedEmbeddingAdapter",
	"ContextualizedEmbeddingsAdapter",
	"resolve_contextualized_embeddings_adapter",
]
