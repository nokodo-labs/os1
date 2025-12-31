"""embedding adapter union - single entry point for all embedding adapters."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from nokodo_ai.adapters.base.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.ollama.embedding import OllamaEmbeddingAdapter
from nokodo_ai.adapters.openai.embedding import OpenAIEmbeddingAdapter


EmbeddingAdapter = Annotated[
	OpenAIEmbeddingAdapter | OllamaEmbeddingAdapter,
	Field(discriminator="type"),
]


def resolve_embedding_adapter_type(provider: str, api: str | None) -> str | None:
	"""resolve the adapter type string from provider and api."""
	if provider == "openai":
		return "openai.embedding"
	if provider == "ollama":
		return "ollama.embedding"
	return None


__all__ = [
	"BaseEmbeddingAdapter",
	"EmbeddingAdapter",
	"resolve_embedding_adapter_type",
]
