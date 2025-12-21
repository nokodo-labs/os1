"""ollama provider adapters."""

from __future__ import annotations

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter
from nokodo_ai.adapters.ollama.chat import OllamaChatAdapter
from nokodo_ai.adapters.ollama.embedding import OllamaEmbeddingAdapter


def get_chat_adapter(variant: str | None, model: str) -> BaseChatAdapter:
	"""get ollama chat adapter by variant.

	args:
		variant: adapter variant name, or None for default
		model: model identifier

	returns:
		the appropriate chat adapter instance

	raises:
		ValueError: if variant is unknown
	"""
	if variant is not None:
		raise ValueError(f"unknown ollama chat adapter variant: {variant}")
	# default chat adapter
	return OllamaChatAdapter(model=model)


def get_embedding_adapter(variant: str | None, model: str) -> BaseEmbeddingAdapter:
	"""get ollama embedding adapter by variant.

	args:
		variant: adapter variant name, or None for default
		model: model identifier

	returns:
		the appropriate embedding adapter instance

	raises:
		ValueError: if variant is unknown
	"""
	if variant is not None:
		raise ValueError(f"unknown ollama embedding adapter variant: {variant}")
	# default embedding adapter
	return OllamaEmbeddingAdapter(model=model)


__all__ = [
	"BaseOllamaAdapter",
	"OllamaChatAdapter",
	"OllamaEmbeddingAdapter",
	"get_chat_adapter",
	"get_embedding_adapter",
]
