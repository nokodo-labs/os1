"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

from nokodo_ai.adapter_enabled import AdapterEnabledMixin
from nokodo_ai.adapters.chat import (
	BaseChatAdapter,
	ChatGenerationParams,
	resolve_adapter,
	split_model_identifier,
)
from nokodo_ai.deltas import ChatModelDelta, stream_chat_model_deltas
from nokodo_ai.messages import AssistantMessage, Message
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool


class ChatModel(ChatGenerationParams, AdapterEnabledMixin[BaseChatAdapter]):
	"""high-level unified interface for LLM chat models.

	usage (defaults):
		llm = ChatModel("gpt-4o")  # uses default provider and adapter
		response = await llm.generate(messages)

		async for delta in llm.generate(messages, stream=True):
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

		response = await llm.generate(thread, tools=[get_weather])

	usage (structured output):
		schema = {
			"type": "object",
			"properties": {"name": {"type": "string"}},
			"required": ["name"],
		}
		params = ChatGenerationParams(response_model=schema)
		response = await llm.generate(messages, params=params)
		data = response.json  # parsed JSON data
	"""

	def _resolve_adapter_from_model(self, model: str) -> BaseChatAdapter:
		return resolve_adapter(model)

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[ChatModelDelta]: ...

	def generate(
		self,
		input: list[Message] | Thread,
		stream: bool = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[ChatModelDelta]:
		"""generate an assistant response.

		args:
			input: list of messages or a Thread to generate from
			stream: whether to stream the response
			tools: list of tools the model can call
			params: generation parameters (tool choice, schema, sampling settings)

		usage:
			response = await llm.generate(messages)
			async for chunk in llm.generate(messages, stream=True):
				...
		"""
		messages: list[Message]
		if isinstance(input, Thread):
			messages = input.messages
		else:
			messages = input

		effective_params = self.model_copy(update={})
		if tool_choice is None:
			effective_params.tool_choice = "auto" if tools else None
		else:
			effective_params.tool_choice = tool_choice
		if params is not None:
			if isinstance(params, dict):
				params = ChatGenerationParams.model_validate(params)
			effective_params = effective_params.model_copy(
				update=params.model_dump(exclude_none=True)
			)

		_model_provider, _model_variant, model_name = split_model_identifier(self.model)
		if stream:
			raw_stream = self._adapter_resolved.generate(
				messages,
				model=model_name,
				stream=True,
				tools=tools,
				params=effective_params,
			)
			return stream_chat_model_deltas(raw_stream)
		return self._adapter_resolved.generate(
			messages,
			model=model_name,
			stream=False,
			tools=tools,
			params=effective_params,
		)
