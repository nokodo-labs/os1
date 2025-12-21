"""ollama chat adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class OllamaChatAdapter(BaseOllamaAdapter, BaseChatAdapter):
	"""adapter for ollama's chat API."""

	def __init__(
		self,
		*,
		model: str = "llama3.2",
		base_url: str = "http://localhost:11434",
		timeout: float = 120.0,
	) -> None:
		"""initialize ollama chat adapter.

		args:
			model: model name (e.g., "llama3.2", "mistral")
			base_url: ollama server URL
			timeout: request timeout in seconds
		"""
		super().__init__(base_url=base_url, timeout=timeout)
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
		"""generate a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")

	async def _stream(self, messages: list[Message]) -> AsyncIterator[Message]:
		"""stream a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")
