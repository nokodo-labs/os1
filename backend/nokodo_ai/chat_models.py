"""chat model high-level interface - unified access to chat models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import Any, ClassVar, Literal, overload

from pydantic import Field

from .adapter_enabled import AdapterEnabledBase, AdapterResolver
from .adapters.base.chat import ChatGenerationParams
from .adapters.chat import ChatAdapter, resolve_chat_adapter
from .deltas import ChatModelDelta, stream_chat_model_deltas
from .messages import AssistantMessage, Message
from .threads import Thread
from .tool import ToolDefinition


class ChatModel(ChatGenerationParams, AdapterEnabledBase[ChatAdapter]):
	"""high-level unified interface for chat models.

	usage:
		chat_model = ChatModel.create(
			"gpt-4o",
			adapter={"type": "openai", "api_key": "..."},
		)
		response = await chat_model.generate(messages)
	"""

	model_name: str = Field(..., description="model identifier")

	_adapter_resolver: ClassVar[AdapterResolver] = resolve_chat_adapter

	@classmethod
	def create(
		cls,
		model_name: str,
		adapter: ChatAdapter | dict[str, Any],
		**fields: Any,
	) -> ChatModel:
		"""Create a chat model with explicit adapter configuration.

		- `model_name` is positional for minimal call sites.
		- `adapter` can be a dict (recommended) or an adapter instance.
		- `adapter.type` may be a shorthand provider name like `openai`.
		"""
		return super()._create(("model_name", model_name), adapter=adapter, **fields)

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

	async def cancel_generation(self, latest_message: AssistantMessage) -> bool:
		"""ask the adapter to cancel an in-flight generation server-side.

		callers should also close their stream context; this method only
		handles provider-side termination to stop generating tokens that
		will not be consumed.

		:param latest_message: the accumulated ``AssistantMessage`` built
			from streaming deltas. the adapter extracts whatever
			provider-specific id it needs from the message metadata.
		:returns: True if the provider acknowledged the cancel, False
			otherwise (unsupported or already finished).
		"""
		return await self.adapter.cancel_generation(latest_message)
