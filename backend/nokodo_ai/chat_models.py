"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, Literal, overload

from pydantic import model_validator

from nokodo_ai.adapter_enabled import AdapterEnabledMixin, split_model_identifier
from nokodo_ai.adapters.base.chat import ChatGenerationParams
from nokodo_ai.adapters.chat import ChatAdapter, resolve_chat_adapter_type
from nokodo_ai.deltas import ChatModelDelta, stream_chat_model_deltas
from nokodo_ai.messages import AssistantMessage, Message
from nokodo_ai.thread import Thread
from nokodo_ai.tool import Tool


class ChatModel(ChatGenerationParams, AdapterEnabledMixin[ChatAdapter]):
	"""high-level unified interface for LLM chat models.

	usage (defaults):
		llm = ChatModel("gpt-4o")
		response = await llm.generate(messages)

	usage (explicit adapter config):
		llm = ChatModel(
			"openai:gpt-4o",
			adapter={"api_key": "..."}
		)
	"""

	@model_validator(mode="before")
	@classmethod
	def resolve_adapter_config(cls, data: Any) -> Any:
		"""resolve adapter configuration from input data."""
		if isinstance(data, dict):
			model = data.pop("model_name", None)
			if model and isinstance(model, str):
				provider, api, name = split_model_identifier(model)
				data.setdefault("provider", provider)
				data.setdefault("api", api)
				data.setdefault("model_name", name)

			if "adapter" not in data:
				provider = data.get("provider")
				api = data.get("api")

				if provider:
					adapter_type = resolve_chat_adapter_type(provider, api)
					if adapter_type:
						adapter_config = {"type": adapter_type}
						data["adapter"] = adapter_config

		return data

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[False] = False,
		tools: list[Tool] = [],
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[True],
		tools: list[Tool] = [],
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[ChatModelDelta]: ...

	def generate(
		self,
		input: list[Message] | Thread,
		stream: bool = False,
		tools: list[Tool] = [],
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[ChatModelDelta]:
		"""generate an assistant response."""
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

		if stream:
			raw_stream = self.adapter.generate(
				messages,
				model=self.model_name,
				stream=True,
				tools=tools,
				params=effective_params,
			)
			return stream_chat_model_deltas(raw_stream)
		return self.adapter.generate(
			messages,
			model=self.model_name,
			stream=False,
			tools=tools,
			params=effective_params,
		)
