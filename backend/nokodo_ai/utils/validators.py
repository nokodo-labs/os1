"""validation utilities.

these are intentionally small, runtime-safe helpers that also improve typing.
"""

from __future__ import annotations

from typing import Literal, cast, get_args, get_origin

from typing_extensions import TypeForm


def validate_literal[T](value: object, literal_type: TypeForm[T] | object) -> T:
	"""validate that a value is one of the values in a Literal[...] type."""
	if get_origin(literal_type) is not Literal:
		raise TypeError("literal_type must be a typing.Literal[...] type")

	allowed = get_args(literal_type)
	if not allowed:
		raise TypeError("literal_type must include at least one literal value")

	if value not in allowed:
		raise ValueError(f"invalid value: {value!r}. allowed: {list(allowed)!r}")

	return cast(T, value)
