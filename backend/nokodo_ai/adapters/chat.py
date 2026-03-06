"""chat adapter union - single entry point for all chat adapters."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from .anthropic.messages import AnthropicMessagesAdapter
from .base.chat import (
	BaseChatAdapter,
	ChatGenerationParams,
)
from .google.generate_content import GoogleGenerateContentAdapter
from .ollama.chat import OllamaChatAdapter
from .openai.chat_completions import OpenAIChatCompletionsAdapter
from .openai.responses import OpenAIResponsesAdapter


ChatAdapter = Annotated[
	OpenAIChatCompletionsAdapter
	| OpenAIResponsesAdapter
	| AnthropicMessagesAdapter
	| GoogleGenerateContentAdapter
	| OllamaChatAdapter,
	Field(discriminator="type"),
]


def resolve_chat_adapter(provider: str, adapter: str | None) -> str | None:
	"""resolve the adapter type string from provider and adapter variant."""
	match provider:
		case "openai":
			if adapter == "responses":
				return "openai.responses"
			return "openai.chat_completions"
		case "anthropic":
			return "anthropic.messages"
		case "google":
			return "google.generate_content"
		case "ollama":
			return "ollama.chat"
	return None


__all__ = [
	"BaseChatAdapter",
	"ChatAdapter",
	"ChatGenerationParams",
	"resolve_chat_adapter",
]
