"""anthropic messages adapter - /v1/messages endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from nokodo_ai.adapters.anthropic.base import BaseAnthropicAdapter
from nokodo_ai.adapters.chat import BaseChatAdapter


if TYPE_CHECKING:
	from nokodo_ai.message import Message


class AnthropicMessagesAdapter(BaseAnthropicAdapter, BaseChatAdapter):
	"""adapter for anthropic's /v1/messages endpoint."""

	def __init__(
		self,
		*,
		model: str = "claude-sonnet-4-20250514",
		api_key: str | None = None,
		timeout: float = 60.0,
	) -> None:
		"""initialize messages adapter.

		args:
			model: model identifier (e.g., "claude-sonnet-4-20250514")
			api_key: anthropic API key
			timeout: request timeout in seconds
		"""
		super().__init__(api_key=api_key, timeout=timeout)
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
		"""generate a completion using anthropic messages API."""
		raise NotImplementedError("anthropic messages adapter not yet implemented")

	async def _stream(self, messages: list[Message]) -> AsyncIterator[Message]:
		"""stream a completion using anthropic messages API."""
		raise NotImplementedError("anthropic messages adapter not yet implemented")
