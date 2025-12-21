"""openai chat completions adapter - /v1/chat/completions endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
	OpenAIChatCompletionAssistantMessageParam,
	OpenAIChatCompletionFunctionToolCall,
	OpenAIChatCompletionFunctionToolCallParam,
	OpenAIChatCompletionMessageParam,
	OpenAIChatCompletionSystemMessageParam,
	OpenAIChatCompletionToolMessageParam,
	OpenAIChatCompletionUserMessageParam,
)
from nokodo_ai.message import (
	AssistantMessage,
	SystemMessage,
	ToolCall,
	ToolMessage,
	UserMessage,
)


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class OpenAIChatCompletionsAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/chat/completions endpoint.

	this is the standard openai chat API used by most applications.
	"""

	def __init__(
		self,
		*,
		model: str = "gpt-4o",
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize chat completions adapter.

		args:
			model: model identifier (e.g., "gpt-4o", "gpt-4o-mini")
			api_key: openai API key
			base_url: custom base URL
			timeout: request timeout in seconds
		"""
		super().__init__(api_key=api_key, base_url=base_url, timeout=timeout)
		self.model = model

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[False] = False,
	) -> Awaitable[Message]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[True],
	) -> AsyncIterator[Message]: ...

	def generate(
		self,
		messages: list[Message],
		*,
		stream: bool = False,
	) -> Awaitable[Message] | AsyncIterator[Message]:
		if stream:
			return self._stream(messages)
		return self._complete(messages)

	async def _complete(self, messages: list[Message]) -> Message:
		"""generate a completion using /v1/chat/completions."""
		client = self._get_client()
		response = await client.chat.completions.create(
			model=self.model,
			messages=_messages_to_openai_chat_completions(messages),
		)
		if not response.choices:
			return AssistantMessage(content="")
		openai_message = response.choices[0].message
		content = openai_message.content or ""
		tool_calls: list[ToolCall] | None = None
		if openai_message.tool_calls:
			tool_calls = []
			for tool_call in openai_message.tool_calls:
				if isinstance(tool_call, OpenAIChatCompletionFunctionToolCall):
					tool_calls.append(
						ToolCall(
							id=tool_call.id,
							name=tool_call.function.name,
							arguments=tool_call.function.arguments,
						)
					)
		return AssistantMessage(content=content, tool_calls=tool_calls)

	async def _stream(self, messages: list[Message]) -> AsyncIterator[Message]:
		"""stream a completion using /v1/chat/completions."""
		client = self._get_client()
		stream = await client.chat.completions.create(
			model=self.model,
			messages=_messages_to_openai_chat_completions(messages),
			stream=True,
		)
		async for chunk in stream:
			if not chunk.choices:
				continue
			delta = chunk.choices[0].delta
			text = delta.content
			if text:
				yield AssistantMessage(content=text)


def _messages_to_openai_chat_completions(
	messages: list[Message],
) -> list[OpenAIChatCompletionMessageParam]:
	"""convert SDK messages into OpenAI chat.completions message params."""
	openai_messages: list[OpenAIChatCompletionMessageParam] = []
	for message in messages:
		match message:
			case UserMessage():
				openai_messages.append(
					OpenAIChatCompletionUserMessageParam(
						role="user",
						content=message.content,
					)
				)
			case SystemMessage():
				openai_messages.append(
					OpenAIChatCompletionSystemMessageParam(
						role="system",
						content=message.content,
					)
				)
			case AssistantMessage():
				openai_message = OpenAIChatCompletionAssistantMessageParam(
					role="assistant",
					content=message.content,
				)
				if message.tool_calls:
					openai_message["tool_calls"] = [
						OpenAIChatCompletionFunctionToolCallParam(
							id=tool_call.id,
							type="function",
							function={
								"name": tool_call.name,
								"arguments": tool_call.arguments,
							},
						)
						for tool_call in message.tool_calls
					]
				openai_messages.append(openai_message)
			case ToolMessage():
				for tool_result in message.tool_results:
					openai_messages.append(
						OpenAIChatCompletionToolMessageParam(
							role="tool",
							tool_call_id=tool_result.tool_call_id,
							content=tool_result.content,
						)
					)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages
