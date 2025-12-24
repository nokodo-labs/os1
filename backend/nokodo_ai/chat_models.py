"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.message import AssistantMessage, Message
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from nokodo_ai.thread import Thread
	from nokodo_ai.tool import Tool


DEFAULT_PROVIDER = "openai"


class ChatModel:
	"""high-level unified interface for LLM chat models.

	usage (defaults):
		llm = ChatModel("gpt-4o")  # uses default provider and adapter
		response = await llm.generate(messages)

		async for chunk in llm.generate(messages, stream=True):
			...

	usage (explicit adapter):
		from nokodo_ai.adapters.openai import OpenAIResponsesAdapter
		adapter = OpenAIResponsesAdapter(api_key="...")
		llm = ChatModel("openai:gpt-4o", adapter=adapter)

	usage (with tools):
		from nokodo_ai import tool

		@tool(
			description="get weather for a city",
			parameters={
				"type": "object",
				"properties": {"city": {"type": "string"}},
				"required": ["city"],
			},
		)
		def get_weather(city: str) -> str:
			return f"sunny in {city}"

		response = await llm.generate(
			thread,
			tools=[get_weather],
			tool_choice="auto",
		)

	usage (structured output):
		schema = {
			"type": "object",
			"properties": {"name": {"type": "string"}},
			"required": ["name"],
		}
		response = await llm.generate(messages, response_model=schema)
		data = response.json  # parsed JSON data
	"""

	def __init__(
		self,
		model: str = "",
		*,
		adapter: BaseChatAdapter | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> None:
		"""initialize ChatModel interface.

		args:
			model: model identifier with optional provider and adapter type
				prefix: [provider[.api]:]model (e.g., "gpt-4o",
				"openai:gpt-4o", "openai.responses:gpt-4o")
			adapter: explicit adapter instance (overrides model string)
			temperature: default sampling temperature for generations
			max_tokens: default max tokens for generations
		"""
		self.temperature = temperature
		self.max_tokens = max_tokens

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
		input: list[Message] | Thread,
		*,
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		*,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		input: list[Message] | Thread,
		*,
		stream: bool = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		"""generate an assistant response.

		args:
			input: list of messages or a Thread to generate from
			stream: whether to stream the response
			tools: list of tools the model can call
			tool_choice: how to select tools - "auto", "none", "required",
				or a specific tool name
			response_model: JSON Schema for structured output
			temperature: sampling temperature
			max_tokens: maximum tokens to generate

		usage:
			response = await llm.generate(messages)
			async for chunk in llm.generate(messages, stream=True):
				...
		"""
		# convert Thread to list of messages
		from nokodo_ai.thread import Thread

		messages: list[Message]
		if isinstance(input, Thread):
			messages = input.messages
		else:
			messages = input

		adapter_tool_choice = tool_choice if tools else None
		# per-call overrides instance defaults
		effective_temp = temperature if temperature is not None else self.temperature
		effective_max = max_tokens if max_tokens is not None else self.max_tokens

		if stream:
			return self._adapter.generate(
				messages,
				stream=True,
				tools=tools,
				tool_choice=adapter_tool_choice,
				response_model=response_model,
				temperature=effective_temp,
				max_tokens=effective_max,
			)
		return self._adapter.generate(
			messages,
			stream=False,
			tools=tools,
			tool_choice=adapter_tool_choice,
			response_model=response_model,
			temperature=effective_temp,
			max_tokens=effective_max,
		)
