"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, Literal, overload

from pydantic import model_validator

from .adapter_enabled import AdapterEnabledMixin, split_model_identifier
from .adapters.base.chat import ChatGenerationParams
from .adapters.chat import ChatAdapter, resolve_chat_adapter
from .deltas import ChatModelDelta, stream_chat_model_deltas
from .messages import AssistantMessage, Message
from .thread import Thread
from .tool import ToolDefinition


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

	def __init__(self, model_name: str | None = None, **data: Any) -> None:
		# convenience: allow `ChatModel("gpt-4o")`
		if model_name is not None:
			data["model_name"] = model_name
		super().__init__(**data)

	@model_validator(mode="before")
	@classmethod
	def resolve_adapter_config(cls, data: Any) -> Any:
		"""resolve adapter configuration from input data."""
		if isinstance(data, dict):
			model = data.pop("model_name", None)
			if model and isinstance(model, str):
				provider, variant, name = split_model_identifier(model)
				data.setdefault("provider", provider)
				data.setdefault("variant", variant)
				data.setdefault("model_name", name)

			# If an adapter dict is provided but uses a shorthand type (e.g. "openai"),
			# expand it to the fully-qualified discriminator tag expected by
			# ChatAdapter.
			adapter = data.get("adapter")
			if isinstance(adapter, dict):
				type_value = adapter.get("type")
				if isinstance(type_value, str) and "." not in type_value:
					provider = str(data.get("provider") or type_value)
					variant = data.get("variant")
					adapter_type = resolve_chat_adapter(provider, variant)
					if not adapter_type:
						raise ValueError(f"unknown provider: {provider}")
					adapter["type"] = adapter_type
					data.setdefault("provider", provider)

			if "adapter" not in data:
				provider = data.get("provider")
				variant = data.get("variant")

				if provider:
					adapter_type = resolve_chat_adapter(provider, variant)
					if not adapter_type:
						raise ValueError(f"unknown provider: {provider}")
					adapter_config = {"type": adapter_type}
					data["adapter"] = adapter_config

		return data

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[False] = False,
		tools: list[ToolDefinition] = [],
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		input: list[Message] | Thread,
		stream: Literal[True],
		tools: list[ToolDefinition] = [],
		tool_choice: Literal["auto", "none", "required"] | str | None = None,
		params: ChatGenerationParams | dict[str, object] | None = None,
	) -> AsyncIterator[ChatModelDelta]: ...

	def generate(
		self,
		input: list[Message] | Thread,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
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
