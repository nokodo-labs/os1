"""openai responses adapter - /v1/responses endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.openai.base import BaseOpenAIAdapter
from nokodo_ai.adapters.openai.types import (
	OpenAIEasyInputMessageParam,
	OpenAIResponseInputParam,
	OpenAIResponseTextDeltaEvent,
)
from nokodo_ai.message import AssistantMessage, SystemMessage, ToolMessage, UserMessage


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class OpenAIResponsesAdapter(BaseOpenAIAdapter, BaseChatAdapter):
	"""adapter for openai's /v1/responses endpoint.

	this is the newer responses API with built-in tool handling.
	"""

	def __init__(
		self,
		*,
		model: str = "gpt-4o",
		api_key: str | None = None,
		base_url: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize responses adapter.

		args:
			model: model identifier
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
		"""generate a completion using /v1/responses."""
		response = await self.client.responses.create(
			model=self.model,
			input=_messages_to_openai_responses_input(messages),
		)
		return AssistantMessage(content=response.output_text or "")

	async def _stream(self, messages: list[Message]) -> AsyncIterator[Message]:
		"""stream a completion using /v1/responses."""
		stream = await self.client.responses.create(
			model=self.model,
			input=_messages_to_openai_responses_input(messages),
			stream=True,
		)
		async for event in stream:
			if isinstance(event, OpenAIResponseTextDeltaEvent):
				if event.delta:
					yield AssistantMessage(content=event.delta)


def _messages_to_openai_responses_input(
	messages: list[Message],
) -> OpenAIResponseInputParam:
	"""convert SDK messages into OpenAI Responses 'easy' message inputs."""
	openai_messages: OpenAIResponseInputParam = []
	for message in messages:
		match message:
			case UserMessage():
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="user",
						content=message.content,
					)
				)
			case SystemMessage():
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="system",
						content=message.content,
					)
				)
			case AssistantMessage():
				openai_messages.append(
					OpenAIEasyInputMessageParam(
						type="message",
						role="assistant",
						content=message.content,
					)
				)
			case ToolMessage():
				tool_text = "\n".join(
					f"{tool_result.tool_call_id}: {tool_result.content}"
					for tool_result in message.tool_results
				)
				if tool_text:
					openai_messages.append(
						OpenAIEasyInputMessageParam(
							type="message",
							role="assistant",
							content=f"tool output:\n{tool_text}",
						)
					)
			case _:
				raise TypeError(f"unsupported message type: {type(message)}")
	return openai_messages
