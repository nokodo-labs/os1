"""base chat adapter - capability ABC for chat completions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload


if TYPE_CHECKING:
	from nokodo_ai.message import AssistantMessage, Message
	from nokodo_ai.tool import Tool

from nokodo_ai.types.json import JSONObject


class BaseChatAdapter(ABC):
	"""capability ABC for chat completion APIs.

	adapters implementing this interface provide:
	- generate(): single-shot completion or streaming completion

	the same interface shape works across different API endpoints
	(e.g., /v1/chat/completions vs /v1/responses).
	"""

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

	@abstractmethod
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
		"""generate a response.

		usage:
			message = await adapter.generate(messages)
			async for chunk in adapter.generate(messages, stream=True):
				...
		"""
		...
