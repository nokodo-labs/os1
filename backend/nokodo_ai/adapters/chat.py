"""chat adapter union - single entry point for all chat adapters."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .anthropic.messages import AnthropicMessagesAdapter
from .base.chat import (
	BaseChatAdapter,
	ChatGenerationParams,
)
from .ollama.chat import OllamaChatAdapter
from .openai.chat_completions import OpenAIChatCompletionsAdapter
from .openai.responses import OpenAIResponsesAdapter


ChatAdapter = Annotated[
	OpenAIChatCompletionsAdapter
	| OpenAIResponsesAdapter
	| AnthropicMessagesAdapter
	| OllamaChatAdapter,
	Field(discriminator="type"),
]


def resolve_chat_adapter_type(provider: str, api: str | None) -> str | None:
	"""resolve the adapter type string from provider and api."""
	match provider:
		case "openai":
			if api == "responses":
				return "openai.responses"
			return "openai.chat_completions"
		case "anthropic":
			return "anthropic.messages"
		case "ollama":
			return "ollama.chat"
	return None


__all__ = [
	"BaseChatAdapter",
	"ChatAdapter",
	"ChatGenerationParams",
	"resolve_chat_adapter_type",
]
