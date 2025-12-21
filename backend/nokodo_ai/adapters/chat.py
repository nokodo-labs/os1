"""base chat adapter - capability ABC for chat completions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload


if TYPE_CHECKING:
	from nokodo_ai.message import Message


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
	) -> Awaitable[Message]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		*,
		stream: Literal[True],
	) -> AsyncIterator[Message]: ...

	@abstractmethod
	def generate(
		self,
		messages: list[Message],
		*,
		stream: bool = False,
	) -> Awaitable[Message] | AsyncIterator[Message]:
		"""generate a response.

		usage:
			message = await adapter.generate(messages)
			async for chunk in adapter.generate(messages, stream=True):
				...
		"""
		...
