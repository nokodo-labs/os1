"""llm high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Literal, overload

from pydantic import PrivateAttr

from .adapter_enabled import AdapterEnabledBase
from .adapters.base.chat import ChatGenerationParams
from .adapters.chat import ChatAdapter, resolve_chat_adapter
from .deltas import ChatModelDelta, stream_chat_model_deltas
from .messages import AssistantMessage, Message
from .threads import Thread
from .tool import ToolDefinition


class ChatModel(ChatGenerationParams, AdapterEnabledBase[ChatAdapter]):
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

	_adapter_resolver: ... = resolve_chat_adapter

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
