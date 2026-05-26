"""generic exception shape helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class NoArgProviderValue(Protocol):
	def __call__(self) -> object: ...


def status_is_unavailable(status_code: int | None) -> bool:
	return status_code in {500, 502, 503, 529}


def status_code_from_attrs(exc: Exception) -> int | None:
	for value in (
		getattr(exc, "status_code", None),
		response_attr(exc, "status_code"),
	):
		if isinstance(value, int):
			return value
	return None


def error_code(exc: Exception) -> str | None:
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
	return string_key_mapping(getattr(exc, "body", None))


def body_error_value(exc: Exception, key: str) -> object | None:
	body = body_mapping(exc)
	if body is None:
		return None
	error = body.get("error")
	error_body = string_key_mapping(error)
	if error_body is not None and key in error_body:
		return error_body[key]
	return body.get(key)


def string_key_mapping(value: object) -> dict[str, object] | None:
	if not isinstance(value, Mapping):
		return None
	return {key: item for key, item in value.items() if isinstance(key, str)}


def response_attr(exc: Exception, attr: str) -> object | None:
	response = getattr(exc, "response", None)
	if response is None:
		return None
	return getattr(response, attr, None)


def stringify_code(value: object) -> str | None:
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
