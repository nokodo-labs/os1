"""reranker adapter union - single entry point for all reranker adapters."""

from typing import Annotated

from pydantic import Field

from .base.rerankers import BaseRerankerAdapter, RerankResult
from .cohere.rerankers import CohereRerankerAdapter
from .jina.rerankers import JinaRerankerAdapter
from .voyageai.rerankers import VoyageAIRerankerAdapter


RerankerAdapter = Annotated[
	VoyageAIRerankerAdapter | CohereRerankerAdapter | JinaRerankerAdapter,
	Field(discriminator="type"),
]


def resolve_reranker_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider."""
	if provider == "voyageai":
		return "voyageai.rerank"
	if provider == "cohere":
		return "cohere.rerank"
	if provider == "jina":
		return "jina.rerank"
	return None


__all__ = [
	"BaseRerankerAdapter",
	"CohereRerankerAdapter",
	"JinaRerankerAdapter",
	"RerankResult",
	"RerankerAdapter",
	"VoyageAIRerankerAdapter",
	"resolve_reranker_adapter",
]
