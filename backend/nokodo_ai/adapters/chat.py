"""base chat adapter - capability ABC for chat completions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from pydantic import ConfigDict

from nokodo_ai.base import Base


if TYPE_CHECKING:
	from nokodo_ai.message import AssistantMessage, Message
	from nokodo_ai.tool import Tool


from nokodo_ai.types.json import JSONObject


DEFAULT_PROVIDER = "openai"


class ChatGenerationParams(Base):
	"""generation options shared across chat adapters."""

	model_config = ConfigDict(extra="forbid")

	tool_choice: Literal["auto", "none", "required"] | str | None = "auto"
	response_model: JSONObject | None = None
	temperature: float | None = None
	max_tokens: int | None = None
	reasoning_tags: list[str] | None = None
	seed: int | None = None
	stop: list[str] | None = None
	reasoning_effort: Literal["low", "medium", "high"] | None = None
	logit_bias: dict[str, float] | None = None
	top_k: int | None = None
	top_p: float | None = None
	min_p: float | None = None
	frequency_penalty: float | None = None
	presence_penalty: float | None = None
	tfs_z: float | None = None
	repeat_penalty: float | None = None


class BaseChatAdapter(Base, ABC):
	"""capability ABC for chat completion APIs.

	adapters implementing this interface provide:
	- generate(): single-shot completion or streaming completion

	the same interface shape works across different API endpoints
	(e.g., /v1/chat/completions vs /v1/responses).
	"""

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	@abstractmethod
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[Tool] | None = None,
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		"""generate a response.

		usage:
			message = await adapter.generate(messages)
			async for chunk in adapter.generate(messages, stream=True):
				...
		"""
		...


def split_model_identifier(model: str) -> tuple[str, str | None, str]:
	"""split a model identifier into (provider, variant, model_name)."""
	if ":" in model:
		provider_part, model_name = model.split(":", 1)
	else:
		provider_part = DEFAULT_PROVIDER
		model_name = model

	if "." in provider_part:
		provider, variant = provider_part.split(".", 1)
	else:
		provider = provider_part
		variant = None

	return provider, variant, model_name


def resolve_adapter(model: str) -> BaseChatAdapter:
	"""resolve a model string to an adapter instance.

	format: [provider[.variant]:][model_name]
	examples:
		- "gpt-4o" -> default provider's default chat adapter (openai)
		- "openai:gpt-4o" -> openai default chat adapter
		- "openai.responses:gpt-4o" -> openai responses variant
		- "anthropic:claude-sonnet-4-20250514" -> anthropic default chat adapter
		- "ollama:llama3.2" -> ollama default chat adapter
	"""
	provider, variant, model_name = split_model_identifier(model)

	# delegate to provider factory
	match provider:
		case "openai":
			from nokodo_ai.adapters.openai import get_chat_adapter

			return get_chat_adapter(variant)

		case "anthropic":
			from nokodo_ai.adapters.anthropic import get_chat_adapter

			return get_chat_adapter(variant)

		case "ollama":
			from nokodo_ai.adapters.ollama import get_chat_adapter

			return get_chat_adapter(variant)

		case _:
			raise ValueError(f"unknown provider: {provider}")
