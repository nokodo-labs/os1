"""LLM high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.message import AssistantMessage, Message


DEFAULT_PROVIDER = "openai"


class LLM:
	"""high-level unified interface for LLM chat models.

	usage (defaults):
		llm = LLM("gpt-4o")  # uses default provider and adapter
		response = await llm.generate(messages)

		async for chunk in llm.generate(messages, stream=True):
			...

	usage (explicit adapter):
		from nokodo_ai.adapters.openai import OpenAIResponsesAdapter
		adapter = OpenAIResponsesAdapter(api_key="...")
		llm = LLM("openai:gpt-4o", adapter=adapter)
	"""

	def __init__(
		self,
		model: str = "",
		*,
		adapter: BaseChatAdapter | None = None,
	) -> None:
		"""initialize LLM interface.

		args:
			model: model identifier with optional provider and adapter type
				prefix: [provider[.api]:]model (e.g., "gpt-4o",
				"openai:gpt-4o", "openai.responses:gpt-4o")
			adapter: explicit adapter instance (overrides model string)
		"""
		if adapter is not None:
			self.model = model
			self._adapter = adapter
			return

		if model.strip() == "":
			raise ValueError("model must be provided")

		self.model = model
		self._adapter = self._resolve_adapter(model)

	def _resolve_adapter(self, model: str) -> BaseChatAdapter:
		"""resolve a model string to an adapter instance.

		format: [provider[.variant]:][model_name]
		examples:
			- "gpt-4o" -> default provider's default chat adapter (openai)
			- "openai:gpt-4o" -> openai default chat adapter
			- "openai.responses:gpt-4o" -> openai responses variant
			- "anthropic:claude-sonnet-4-20250514" -> anthropic default chat adapter
			- "ollama:llama3.2" -> ollama default chat adapter
		"""
		# parse provider and model from string
		if ":" in model:
			provider_part, model_name = model.split(":", 1)
		else:
			# no provider specified: fallback to default provider
			provider_part = DEFAULT_PROVIDER
			model_name = model

		# parse provider and optional variant
		if "." in provider_part:
			provider, variant = provider_part.split(".", 1)
		else:
			provider = provider_part
			variant = None

		# delegate to provider factory
		match provider:
			case "openai":
				from nokodo_ai.adapters.openai import get_chat_adapter

				return get_chat_adapter(variant, model_name)

			case "anthropic":
				from nokodo_ai.adapters.anthropic import get_chat_adapter

				return get_chat_adapter(variant, model_name)

			case "ollama":
				from nokodo_ai.adapters.ollama import get_chat_adapter

				return get_chat_adapter(variant, model_name)

			case _:
				raise ValueError(f"unknown provider: {provider}")

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[False] = False,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[True],
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		*,
		stream: bool = False,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		"""generate an assistant response.

		usage:
			response = await llm.generate(messages)
			async for chunk in llm.generate(messages, stream=True):
				...
		"""
		if stream:
			return self._generate_stream(messages)
		return self._generate_single(messages)

	async def _generate_single(self, messages: list[Message]) -> AssistantMessage:
		result = await self._adapter.generate(messages)
		if isinstance(result, AssistantMessage):
			return result
		return AssistantMessage(content=str(result))

	async def _generate_stream(
		self,
		messages: list[Message],
	) -> AsyncIterator[AssistantMessage]:
		async for chunk in self._adapter.generate(messages, stream=True):
			if isinstance(chunk, AssistantMessage):
				yield chunk
			else:
				yield AssistantMessage(content=str(chunk))
