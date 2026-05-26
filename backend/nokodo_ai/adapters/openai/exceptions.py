"""openai adapter exception conversion."""

from __future__ import annotations

import openai

from ...utils.error_mapping import (
	error_code,
	status_code_from_attrs,
	status_is_unavailable,
)
from ..base.chat import (
	GenerationAuthenticationError,
	GenerationBadRequestError,
	GenerationError,
	GenerationPermissionError,
	GenerationProviderConnectionError,
	GenerationProviderTimeoutError,
	GenerationProviderUnavailableError,
	GenerationRateLimitError,
	generation_error,
	map_chat_generation_exceptions,
)


def map_generation_error(provider: str, exc: Exception) -> GenerationError | None:
	if isinstance(exc, GenerationError):
		return exc
	if not isinstance(exc, openai.OpenAIError):
		return None
	status_code = status_code_from_attrs(exc)
	code = error_code(exc)
	if isinstance(exc, openai.APITimeoutError):
		return generation_error(
			GenerationProviderTimeoutError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.APIConnectionError):
		return generation_error(
			GenerationProviderConnectionError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.AuthenticationError) or status_code == 401:
		return generation_error(
			GenerationAuthenticationError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.PermissionDeniedError) or status_code == 403:
		return generation_error(
			GenerationPermissionError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.RateLimitError) or status_code == 429:
		return generation_error(
			GenerationRateLimitError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.InternalServerError) or status_is_unavailable(
		status_code
	):
		return generation_error(
			GenerationProviderUnavailableError, provider, exc, status_code, code
		)
	if isinstance(exc, openai.BadRequestError) or status_code == 400:
		return generation_error(
			GenerationBadRequestError, provider, exc, status_code, code
		)
	return generation_error(GenerationError, provider, exc, status_code, code)


map_openai_generation_exceptions = map_chat_generation_exceptions(
	"openai",
	map_generation_error,
)
