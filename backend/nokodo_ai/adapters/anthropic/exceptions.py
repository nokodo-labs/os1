"""anthropic adapter exception conversion."""

from __future__ import annotations

import anthropic

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
	if not isinstance(exc, anthropic.AnthropicError):
		return None
	status_code = status_code_from_attrs(exc)
	code = error_code(exc)
	if isinstance(exc, anthropic.APITimeoutError):
		return generation_error(
			GenerationProviderTimeoutError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.APIConnectionError):
		return generation_error(
			GenerationProviderConnectionError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.AuthenticationError) or status_code == 401:
		return generation_error(
			GenerationAuthenticationError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.PermissionDeniedError) or status_code == 403:
		return generation_error(
			GenerationPermissionError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.RateLimitError) or status_code == 429:
		return generation_error(
			GenerationRateLimitError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.InternalServerError) or status_is_unavailable(
		status_code
	):
		return generation_error(
			GenerationProviderUnavailableError, provider, exc, status_code, code
		)
	if isinstance(exc, anthropic.BadRequestError) or status_code == 400:
		return generation_error(
			GenerationBadRequestError, provider, exc, status_code, code
		)
	return generation_error(GenerationError, provider, exc, status_code, code)


map_anthropic_generation_exceptions = map_chat_generation_exceptions(
	"anthropic",
	map_generation_error,
)
