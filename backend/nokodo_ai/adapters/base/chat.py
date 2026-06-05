"""base chat adapter - capability ABC for chat completions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from inspect import isasyncgenfunction
from typing import (
	TYPE_CHECKING,
	ClassVar,
	Concatenate,
	Literal,
	NoReturn,
	TypeIs,
	overload,
)

from pydantic import ConfigDict

from ...base import Base
from ...exceptions import NokodoAIError
from ...tool import ToolDefinition
from ...types.json import JSONObject
from ...utils.error_mapping import error_text
from .adapter import BaseAdapter


if TYPE_CHECKING:
	from nokodo_ai.messages import AssistantMessage, Message


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
	reasoning_effort: (
		Literal["none", "minimal", "low", "medium", "high", "max"] | None
	) = None
	logit_bias: dict[str, float] | None = None
	top_k: int | None = None
	top_p: float | None = None
	min_p: float | None = None
	frequency_penalty: float | None = None
	presence_penalty: float | None = None
	tfs_z: float | None = None
	repeat_penalty: float | None = None


class GenerationError(NokodoAIError):
	"""base class for chat generation failures raised by chat adapters."""

	reason: ClassVar[str] = "generation_failed"
	user_message: ClassVar[str] = "generation failed"
	default_retryable: ClassVar[bool] = False

	def __init__(
		self,
		message: str | None = None,
		provider: str | None = None,
		status_code: int | None = None,
		code: str | None = None,
		retryable: bool | None = None,
		details: dict[str, object] | None = None,
	) -> None:
		super().__init__(message or self.user_message)
		self.provider = provider
		self.status_code = status_code
		self.code = code
		self.retryable = self.default_retryable if retryable is None else retryable
		self.details = details or {}


class GenerationRateLimitError(GenerationError):
	"""the provider rejected the request because a rate limit was exceeded."""

	reason: ClassVar[str] = "rate_limit_exceeded"
	user_message: ClassVar[str] = "provider rate limit exceeded"
	default_retryable: ClassVar[bool] = True


class GenerationAuthenticationError(GenerationError):
	"""the provider rejected credentials for the generation request."""

	reason: ClassVar[str] = "provider_authentication_failed"
	user_message: ClassVar[str] = "provider authentication failed"


class GenerationPermissionError(GenerationError):
	"""the provider refused access to the requested model or resource."""

	reason: ClassVar[str] = "provider_permission_denied"
	user_message: ClassVar[str] = "provider permission denied"


class GenerationProviderUnavailableError(GenerationError):
	"""the provider was overloaded or temporarily unavailable."""

	reason: ClassVar[str] = "provider_unavailable"
	user_message: ClassVar[str] = "provider temporarily unavailable"
	default_retryable: ClassVar[bool] = True


class GenerationProviderConnectionError(GenerationError):
	"""the adapter could not connect to the provider."""

	reason: ClassVar[str] = "provider_connection_failed"
	user_message: ClassVar[str] = "provider connection failed"
	default_retryable: ClassVar[bool] = True


class GenerationProviderTimeoutError(GenerationError):
	"""the provider request timed out."""

	reason: ClassVar[str] = "provider_timeout"
	user_message: ClassVar[str] = "provider generation timed out"
	default_retryable: ClassVar[bool] = True


class GenerationBadRequestError(GenerationError):
	"""the provider rejected the generation request as invalid."""

	reason: ClassVar[str] = "provider_bad_request"
	user_message: ClassVar[str] = "provider rejected the generation request"


GenerationExceptionMapper = Callable[[str, Exception], GenerationError | None]


def generation_error(
	cls: type[GenerationError],
	provider: str,
	exc: Exception,
	status_code: int | None,
	code: str | None,
	retryable: bool | None = None,
) -> GenerationError:
	return cls(
		message=error_text(exc) or None,
		provider=provider,
		status_code=status_code,
		code=code,
		retryable=retryable,
		details={"provider_error_type": type(exc).__name__},
	)


def raise_mapped_generation_exception(
	mapper: GenerationExceptionMapper,
	provider: str,
	exc: Exception,
) -> NoReturn:
	mapped = mapper(provider, exc)
	if mapped is None:
		raise exc
	raise mapped from exc


class BaseChatAdapter(BaseAdapter, Base, ABC):
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

	async def cancel_generation(self, latest_message: AssistantMessage) -> bool:
		"""cancel a server-side generation given the accumulated message.

		the adapter extracts its own provider run id from the message's
		metadata and uses it to issue a provider-side cancel.

		:param latest_message: the accumulated ``AssistantMessage`` built
			from streaming deltas so far.
		:returns: True if the provider acknowledged the cancel, False
			otherwise (unsupported, already finished, no run_id found, etc).
		"""
		return False


def _is_chat_generation_stream_function[
	ChatAdapterT: object,
	GeneratedT,
	**ParamsT,
](
	func: Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]]
	| Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]],
) -> TypeIs[Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]]]:
	return isasyncgenfunction(func)


class ChatGenerationExceptionMapperDecorator:
	def __init__(self, provider: str, mapper: GenerationExceptionMapper) -> None:
		self.provider = provider
		self.mapper = mapper

	@overload
	def __call__[
		ChatAdapterT: object,
		GeneratedT,
		**ParamsT,
	](
		self,
		func: Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]],
	) -> Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]]: ...

	@overload
	def __call__[
		ChatAdapterT: object,
		GeneratedT,
		**ParamsT,
	](
		self,
		func: Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]],
	) -> Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]]: ...

	def __call__[
		ChatAdapterT: object,
		GeneratedT,
		**ParamsT,
	](
		self,
		func: Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]]
		| Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]],
	) -> (
		Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]]
		| Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]]
	):
		if _is_chat_generation_stream_function(func):
			return self._wrap_stream(func)
		return self._wrap_call(func)

	def _wrap_call[
		ChatAdapterT: object,
		GeneratedT,
		**ParamsT,
	](
		self,
		func: Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]],
	) -> Callable[Concatenate[ChatAdapterT, ParamsT], Awaitable[GeneratedT]]:
		mapper = self.mapper
		provider = self.provider

		@wraps(func)
		async def wrapper(
			adapter: ChatAdapterT,
			*args: ParamsT.args,
			**kwargs: ParamsT.kwargs,
		) -> GeneratedT:
			try:
				return await func(adapter, *args, **kwargs)
			except Exception as exc:
				raise_mapped_generation_exception(mapper, provider, exc)

		return wrapper

	def _wrap_stream[
		ChatAdapterT: object,
		GeneratedT,
		**ParamsT,
	](
		self,
		func: Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]],
	) -> Callable[Concatenate[ChatAdapterT, ParamsT], AsyncIterator[GeneratedT]]:
		mapper = self.mapper
		provider = self.provider

		@wraps(func)
		async def wrapper(
			adapter: ChatAdapterT,
			*args: ParamsT.args,
			**kwargs: ParamsT.kwargs,
		) -> AsyncIterator[GeneratedT]:
			try:
				async for item in func(adapter, *args, **kwargs):
					yield item
			except Exception as exc:
				raise_mapped_generation_exception(mapper, provider, exc)

		return wrapper


def map_chat_generation_exceptions(
	provider: str,
	mapper: GenerationExceptionMapper,
) -> ChatGenerationExceptionMapperDecorator:
	return ChatGenerationExceptionMapperDecorator(provider, mapper)
