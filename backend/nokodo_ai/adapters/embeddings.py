"""embedding adapter union - single entry point for all embedding adapters."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .base.embeddings import BaseEmbeddingAdapter, EmbeddingInputType
from .ollama.embeddings import OllamaEmbeddingsAdapter
from .openai.embeddings import OpenAIEmbeddingsAdapter
from .voyageai.embeddings import VoyageAIEmbeddingsAdapter


EmbeddingsAdapter = Annotated[
	OpenAIEmbeddingsAdapter | OllamaEmbeddingsAdapter | VoyageAIEmbeddingsAdapter,
	Field(discriminator="type"),
]


def resolve_embeddings_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and api."""
	if provider == "openai":
		return "openai.embedding"
	if provider == "ollama":
		return "ollama.embedding"
	if provider == "voyageai":
		return "voyageai.embedding"
	return None


__all__ = [
	"BaseEmbeddingAdapter",
	"EmbeddingInputType",
	"EmbeddingsAdapter",
	"resolve_embeddings_adapter",
]
