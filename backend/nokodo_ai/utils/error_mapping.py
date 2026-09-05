"""generic exception shape helpers."""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class NoArgProviderValue(Protocol):
	def __call__(self) -> object:
		"""return a provider value without arguments."""
		...


def status_is_unavailable(status_code: int | None) -> bool:
	"""return whether an HTTP status indicates provider unavailability."""
	return status_code in {500, 502, 503, 529}


def status_code_from_attrs(exc: Exception) -> int | None:
	"""extract an HTTP status code from a provider exception."""
	for value in (
		getattr(exc, "status_code", None),
		response_attr(exc, "status_code"),
	):
		if isinstance(value, int):
			return value
	return None


def error_code(exc: Exception) -> str | None:
	"""extract a normalized provider error code from an exception."""
	for value in (
		getattr(exc, "code", None),
		body_error_value(exc, "code"),
		body_error_value(exc, "type"),
		body_error_value(exc, "status"),
		response_attr(exc, "reason_phrase"),
	):
		code = stringify_code(value)
		if code:
			return code
	return None


def error_text(exc: Exception) -> str:
	"""build deduplicated text from common provider error fields."""
	parts: list[str] = []
	for value in (
		getattr(exc, "message", None),
		body_error_value(exc, "message"),
		body_error_value(exc, "code"),
		body_error_value(exc, "type"),
		response_attr(exc, "text"),
		str(exc),
	):
		if value is None:
			continue
		text = str(value).strip()
		if text and text not in parts:
			parts.append(text)
	return " ".join(parts)


def body_mapping(exc: Exception) -> dict[str, object] | None:
	"""return the exception body as a string-keyed mapping."""
	return string_key_mapping(getattr(exc, "body", None))


def body_error_value(exc: Exception, key: str) -> object | None:
	"""read a value from a nested or top-level provider error body."""
	body = body_mapping(exc)
	if body is None:
		return None
	error = body.get("error")
	error_body = string_key_mapping(error)
	if error_body is not None and key in error_body:
		return error_body[key]
	return body.get(key)


def string_key_mapping(value: object) -> dict[str, object] | None:
	"""copy a mapping while retaining only string-keyed entries."""
	if not isinstance(value, Mapping):
		return None
	return {key: item for key, item in value.items() if isinstance(key, str)}


def response_attr(exc: Exception, attr: str) -> object | None:
	"""safely read an attribute from an exception's response."""
	response = getattr(exc, "response", None)
	if response is None:
		return None
	try:
		return getattr(response, attr, None)
	except Exception:
		return None


def stringify_code(value: object) -> str | None:
	"""normalize a provider error-code value to non-empty text."""
	if value is None:
		return None
	if isinstance(value, NoArgProviderValue):
		try:
			value = value()
		except Exception:
			return None
	if isinstance(value, int):
		return str(value)
	if isinstance(value, str):
		return value.strip() or None
	name = getattr(value, "name", None)
	if isinstance(name, str) and name:
		return name
	text = str(value).strip()
	return text or None
