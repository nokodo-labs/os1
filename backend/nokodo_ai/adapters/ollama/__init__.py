"""ollama provider adapters."""

from __future__ import annotations

from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter
from nokodo_ai.adapters.ollama.chat import OllamaChatAdapter
from nokodo_ai.adapters.ollama.embedding import OllamaEmbeddingAdapter


__all__ = [
	"BaseOllamaAdapter",
	"OllamaChatAdapter",
	"OllamaEmbeddingAdapter",
]
