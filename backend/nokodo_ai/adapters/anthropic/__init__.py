"""anthropic provider adapters."""

from __future__ import annotations

from nokodo_ai.adapters.anthropic.base import BaseAnthropicAdapter
from nokodo_ai.adapters.anthropic.messages import AnthropicMessagesAdapter
from nokodo_ai.adapters.chat import BaseChatAdapter


def get_chat_adapter(variant: str | None, model: str) -> BaseChatAdapter:
	"""get anthropic chat adapter by variant.

	args:
		variant: adapter variant name, or None for default
		model: model identifier

	returns:
		the appropriate chat adapter instance

	raises:
		ValueError: if variant is unknown
	"""
	if variant is not None:
		raise ValueError(f"unknown anthropic chat adapter variant: {variant}")
	# default chat adapter
	return AnthropicMessagesAdapter(model=model)


__all__ = [
	"AnthropicMessagesAdapter",
	"BaseAnthropicAdapter",
	"get_chat_adapter",
]
