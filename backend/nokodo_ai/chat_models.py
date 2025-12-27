"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

from pydantic import Field, PrivateAttr, ValidationError, model_validator

from nokodo_ai.adapters.chat import (
	BaseChatAdapter,
	ChatGenerationParams,
	resolve_adapter,
)
from nokodo_ai.base import Base
from nokodo_ai.message import AssistantMessage, Message
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool


class ChatModel(ChatGenerationParams, Base):
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

	model: str = Field(
		...,
		description="model identifier with optional provider and adapter type prefix",
	)
	adapter: BaseChatAdapter | None = Field(
		default=None,
		exclude=True,
		description="chat adapter instance",
	)
	_adapter_resolved: BaseChatAdapter = PrivateAttr()

	@model_validator(mode="before")
	@classmethod
	def _resolve_adapter(cls, values: dict) -> dict:
		adapter = values.get("adapter", None)

		if adapter is None:
			model = values.get("model")
			if model is None:
				raise ValidationError("couldn't resolve adapter: model is required")
			adapter = resolve_adapter(model)
			values["_adapter_resolved"] = adapter
		return values

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[False] = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		input: list[Message] | Thread,
		stream: bool = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
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
		if tool_choice is not None:
			effective_params.tool_choice = tool_choice
		if params is not None:
			if isinstance(params, dict):
				params = ChatGenerationParams.model_validate(params)
			effective_params = effective_params.model_copy(
				update=params.model_dump(exclude_none=True)
			)

		if stream:
			return self._adapter_resolved.generate(
				messages,
				stream=True,
				tools=tools,
				params=effective_params,
			)
		return self._adapter_resolved.generate(
			messages,
			stream=False,
			tools=tools,
			params=effective_params,
		)
