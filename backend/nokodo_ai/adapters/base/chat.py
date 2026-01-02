"""base chat adapter - capability ABC for chat completions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import TYPE_CHECKING, Literal, overload

from pydantic import ConfigDict

from ...base import Base
from ...tool import ToolDefinition


if TYPE_CHECKING:
	from nokodo_ai.messages import AssistantMessage, Message


from nokodo_ai.types.json import JSONObject


class ChatGenerationParams(Base):
	"""generation options shared across chat adapters."""

	model_config = ConfigDict(extra="forbid")

	tool_choice: Literal["auto", "none", "required"] | str | None = "auto"
	response_model: JSONObject | None = None
	temperature: float | None = None
	max_tokens: int | None = None
	reasoning_tags: list[str] | None = None
	seed: int | None = None
	stop: list[str] | None = None
	reasoning_effort: Literal["low", "medium", "high"] | None = None
	logit_bias: dict[str, float] | None = None
	top_k: int | None = None
	top_p: float | None = None
	min_p: float | None = None
	frequency_penalty: float | None = None
	presence_penalty: float | None = None
	tfs_z: float | None = None
	repeat_penalty: float | None = None


class BaseChatAdapter(Base, ABC):
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
		model: str,
		stream: Literal[False] = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage]: ...

	@overload
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: Literal[True],
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> AsyncIterator[AssistantMessage]: ...

	@abstractmethod
	def generate(
		self,
		messages: list[Message],
		model: str,
		stream: bool = False,
		tools: list[ToolDefinition] = [],
		params: ChatGenerationParams | None = None,
	) -> Awaitable[AssistantMessage] | AsyncIterator[AssistantMessage]:
		"""generate a response.

		usage:
			message = await adapter.generate(messages)
			async for chunk in adapter.generate(messages, stream=True):
				...
		"""
		raise NotImplementedError("generate() not implemented in base class")
