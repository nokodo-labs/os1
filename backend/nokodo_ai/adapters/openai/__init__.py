"""openai provider adapters."""

from __future__ import annotations

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.embedding import BaseEmbeddingAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.chat_completions import OpenAIChatCompletionsAdapter
from nokodo_ai.adapters.openai.embedding import OpenAIEmbeddingAdapter
from nokodo_ai.adapters.openai.responses import OpenAIResponsesAdapter


def get_chat_adapter(variant: str | None, model: str) -> BaseChatAdapter:
	"""get openai chat adapter by variant.

	args:
		variant: adapter variant name (e.g., 'responses'), or None for default
		model: model identifier

	returns:
		the appropriate chat adapter instance

	raises:
		ValueError: if variant is unknown
	"""
	match variant:
		case None:
			# default chat adapter
			return OpenAIChatCompletionsAdapter(model=model)
		case "responses":
			return OpenAIResponsesAdapter(model=model)
		case _:
			raise ValueError(f"unknown openai chat adapter variant: {variant}")


def get_embedding_adapter(variant: str | None, model: str) -> BaseEmbeddingAdapter:
	"""get openai embedding adapter by variant.

	args:
		variant: adapter variant name, or None for default
		model: model identifier

	returns:
		the appropriate embedding adapter instance

	raises:
		ValueError: if variant is unknown
	"""
	if variant is not None:
		raise ValueError(f"unknown openai embedding adapter variant: {variant}")
	# default embedding adapter
	return OpenAIEmbeddingAdapter(model=model)


__all__ = [
	"BaseOpenAIAdapter",
	"OpenAIChatCompletionsAdapter",
	"OpenAIEmbeddingAdapter",
	"OpenAIResponsesAdapter",
	"get_chat_adapter",
	"get_embedding_adapter",
]
