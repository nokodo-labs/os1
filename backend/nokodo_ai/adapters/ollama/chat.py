"""ollama chat adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.chat import BaseChatAdapter
from nokodo_ai.adapters.ollama.base import BaseOllamaAdapter
from nokodo_ai.types.json import JSONObject


if TYPE_CHECKING:
	from nokodo_ai.message import AssistantMessage, Message
	from nokodo_ai.tool import Tool


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
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[True],
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	def generate(
		self,
		messages: list[Message],
		*,
		stream: bool = False,
		tools: list[Tool] | None = None,
		tool_choice: Literal["auto", "none", "required"] | str | None = "auto",
		response_model: JSONObject | None = None,
		temperature: float | None = None,
		max_tokens: int | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		# options not yet implemented for ollama adapter
		_ = (tools, tool_choice, response_model, temperature, max_tokens)
		if stream:
			return self._stream(messages)
		return self._complete(messages)

	async def _complete(self, messages: list[Message]) -> AssistantMessage:
		"""generate a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")

	async def _stream(self, messages: list[Message]) -> AsyncIterator[AssistantMessage]:
		"""stream a completion using ollama chat API."""
		raise NotImplementedError("ollama chat adapter not yet implemented")
