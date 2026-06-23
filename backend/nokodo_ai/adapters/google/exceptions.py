"""google adapter exception conversion."""

from __future__ import annotations

from ...utils.error_mapping import (
	NoArgProviderValue,
	error_code,
	response_attr,
	status_is_unavailable,
)
from ..base.chat import (
	GenerationAuthenticationError,
	GenerationBadRequestError,
	GenerationError,
	GenerationPermissionError,
	GenerationProviderTimeoutError,
	GenerationProviderUnavailableError,
	GenerationRateLimitError,
	generation_error,
	map_chat_generation_exceptions,
)


def map_generation_error(provider: str, exc: Exception) -> GenerationError | None:
	if isinstance(exc, GenerationError):
		return exc
	module_name = type(exc).__module__
	if not module_name.startswith(("google.genai", "google.api_core")):
		return None
	status_code = _status_code(exc)
	code = error_code(exc)
	class_name = type(exc).__name__.lower()
	if "timeout" in class_name or status_code in {408, 504}:
		return generation_error(
			GenerationProviderTimeoutError, provider, exc, status_code, code
		)
	if (
		"unauthorized" in class_name
		or "authentication" in class_name
		or status_code == 401
	):
		return generation_error(
			GenerationAuthenticationError, provider, exc, status_code, code
		)
	if "permission" in class_name or "forbidden" in class_name or status_code == 403:
		return generation_error(
			GenerationPermissionError, provider, exc, status_code, code
		)
	if "resourceexhausted" in class_name or status_code == 429:
		return generation_error(
			GenerationRateLimitError, provider, exc, status_code, code
		)
	if "servererror" in class_name or status_is_unavailable(status_code):
		return generation_error(
			GenerationProviderUnavailableError, provider, exc, status_code, code
		)
	if "clienterror" in class_name or status_code == 400:
		return generation_error(
			GenerationBadRequestError, provider, exc, status_code, code
		)
	return generation_error(GenerationError, provider, exc, status_code, code)


map_google_generation_exceptions = map_chat_generation_exceptions(
	"google",
	map_generation_error,
)


def _status_code(exc: Exception) -> int | None:
	for value in (
		getattr(exc, "status_code", None),
		response_attr(exc, "status_code"),
		_google_code_value(getattr(exc, "code", None)),
	):
		if isinstance(value, int):
			return value
	return None


def _google_code_value(value: object) -> int | None:
	if isinstance(value, int):
		return value
	if isinstance(value, NoArgProviderValue):
		try:
			value = value()
		except Exception:
			return None
	if isinstance(value, int):
		return value
	value_attr = getattr(value, "value", None)
	if isinstance(value_attr, int):
		return value_attr
	return None
