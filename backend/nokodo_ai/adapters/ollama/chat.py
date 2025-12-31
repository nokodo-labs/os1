"""ollama chat adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.base.chat import BaseChatAdapter, ChatGenerationParams
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter


if TYPE_CHECKING:
	from nokodo_ai.messages import AssistantMessage, Message
	from nokodo_ai.tool import Tool


class OllamaChatAdapter(BaseOllamaAdapter, BaseChatAdapter):
	"""adapter for ollama's chat API."""

	type: Literal["ollama.chat"] = "ollama.chat"

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		model: str,
		stream: Literal[False] = False,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		model: str,
		stream: Literal[True],
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		*,
		model: str,
		stream: bool = False,
		tools: list[Tool] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		_ = (model, tools, params)
		if stream:
			return self._stream(messages)
		return self._complete(messages)

	async def _complete(self, messages: list[Message]) -> AssistantMessage:
		"""generate a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")

	async def _stream(self, messages: list[Message]) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")
