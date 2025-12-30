"""
validation utilities.

these are intentionally small, runtime-safe helpers that also improve typing.
"""

import types
from typing import Annotated, Literal, Union, cast, get_args, get_origin

from pydantic import TypeAdapter
from typing_extensions import TypeForm


def validate_literal[T](value: object, literal_type: TypeForm[T]) -> T:
	"""validate that a value is one of the values in a Literal[...] type."""
	if get_origin(literal_type) is not Literal:
		raise TypeError("literal_type must be a typing.Literal[...] type")

	allowed = get_args(literal_type)
	if not allowed:
		raise TypeError("literal_type must include at least one literal value")

	if value not in allowed:
		raise ValueError(f"invalid value: {value!r}. allowed: {list(allowed)!r}")

	return cast(T, value)


def validate[T](
	value: object,
	expected_type: TypeForm[T] | object,
	# had to add "| object" to avoid type checker error-
	# TODO: remove when PEP 747 is fully supported
) -> T:
	"""validate that a value is of the expected type."""
	type_origin = get_origin(expected_type)

	if expected_type is None:
		if value is not None:
			raise TypeError(f"expected None, got {type(value)}")

	elif type_origin is Annotated:
		inner_type = get_args(expected_type)[0]
		return validate(value, inner_type)

	elif type_origin in (Union, types.UnionType):
		for arg in get_args(expected_type):
			try:
				return validate(value, arg)
			except (TypeError, ValueError):
				continue
		raise TypeError(f"expected type {expected_type}, got {type(value)}")

	elif type_origin is Literal:
		expected_type = cast(TypeForm[T], expected_type)
		return validate_literal(value, expected_type)

	elif type_origin is None:
		if not isinstance(value, cast(type, expected_type)):
			raise TypeError(f"expected type {expected_type}, got {type(value)}")

	else:
		# let pydantic handle complex types
		expected_type = cast(TypeForm[T], expected_type)
		return _validate_pydantic(value, expected_type)

	return cast(T, value)


def _validate_pydantic[T](value: object, expected_type: TypeForm[T]) -> T:
	"""validate that a value is of the expected pydantic model type."""

	adapter = TypeAdapter(expected_type)
	return cast(T, adapter.validate_python(value))
