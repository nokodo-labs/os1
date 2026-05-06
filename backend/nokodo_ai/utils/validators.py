"""
validation utilities.

these are intentionally small, runtime-safe helpers that also improve typing.
"""

import logging
import types
from collections.abc import Callable
from inspect import Parameter, signature
from typing import (
	Annotated,
	Any,
	Literal,
	TypedDict,
	Union,
	cast,
	get_args,
	get_origin,
	get_type_hints,
)

from pydantic import TypeAdapter
from typing_extensions import TypeForm


log = logging.getLogger(__name__)


def validate_literal[T](value: object, literal_type: TypeForm[T]) -> T:
	"""validate that a value is one of the values in a Literal[...] type."""
	origin = get_origin(literal_type)
	if origin is None and literal_type is Literal:
		origin = Literal
	if origin is not Literal:
		raise TypeError("literal_type must be a typing.Literal[...] type")

	allowed = get_args(literal_type)
	if not allowed:
		raise TypeError("literal_type must include at least one literal value")

	if value not in allowed:
		raise ValueError(f"invalid value: {value!r}. allowed: {list(allowed)!r}")

	return cast(T, value)


def warn_known_model(value: str, known_type: object) -> str:
	"""return value as-is, logging a warning if it is not in the known Literal set."""
	allowed = get_args(known_type)
	if allowed and value not in allowed:
		log.warning(
			"model %r not in known set for %s - passing through",
			value,
			known_type,
		)
	return value


def validate[T](
	value: object,
	expected_type: TypeForm[T] | object,
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
		return validate_literal(value, expected_type)

	elif type_origin is None:
		if not isinstance(expected_type, type):
			raise TypeError(f"expected a type annotation, got {expected_type}")
		if not isinstance(value, expected_type):
			raise TypeError(f"expected type {expected_type}, got {type(value)}")

	else:
		# let pydantic handle complex types
		return _validate_pydantic(value, expected_type)

	return cast(T, value)


def _validate_pydantic[T](value: object, expected_type: TypeForm[T]) -> T:
	"""validate that a value is of the expected pydantic model type."""

	adapter: TypeAdapter[T] = TypeAdapter(expected_type)
	validated = adapter.validate_python(value)
	return validated


class ArgCount(TypedDict):
	min: int
	max: int | None


def types_compatible(actual: Any, expected: Any) -> bool:
	"""check if actual type is compatible with expected type."""
	# exact match
	if actual is expected or actual == expected:
		return True

	actual_origin = get_origin(actual)
	expected_origin = get_origin(expected)

	# if expected is a generic origin, check if actual's origin matches
	if expected_origin is None and actual_origin is not None:
		# expected is `list`, actual is `list[int]` -> compatible
		return actual_origin is expected

	if actual_origin is not None and expected_origin is not None:
		return actual_origin is expected_origin

	# try issubclass for concrete types
	try:
		if isinstance(actual, type) and isinstance(expected, type):
			return issubclass(actual, expected)
	except TypeError:
		pass

	return False


def validate_callable(
	func: Callable,
	expected_arg_types: list[Any] | None = None,
	expected_return_type: Any | None = None,
	expected_arg_names: list[str] | None = None,
	expected_arg_count: ArgCount | None = None,
) -> None:
	"""validate a callable's signature against expected types, names, and arg count.

	raises:
		TypeError: if any validation fails
	"""
	func_name = getattr(func, "__name__", repr(func))
	sig = signature(func)
	params = list(sig.parameters.values())

	try:
		hints = get_type_hints(func)
	except Exception:
		# get_type_hints can fail on some edge cases
		hints = getattr(func, "__annotations__", {})

	# filter out *args and **kwargs
	positional_params = [
		p
		for p in params
		if p.kind not in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
	]

	# validate argument count
	if expected_arg_count is not None:
		min_count = expected_arg_count["min"]
		max_count = expected_arg_count["max"]
		actual_count = len(positional_params)

		if actual_count < min_count:
			raise TypeError(
				f"{func_name}: expected at least {min_count} parameters, "
				f"got {actual_count}"
			)

		if max_count is not None and actual_count > max_count:
			raise TypeError(
				f"{func_name}: expected at most {max_count} parameters, "
				f"got {actual_count}"
			)

	# validate argument names
	if expected_arg_names is not None:
		for i, expected_name in enumerate(expected_arg_names):
			if i >= len(positional_params):
				raise TypeError(
					f"{func_name}: missing parameter '{expected_name}' at position {i}"
				)

			actual_name = positional_params[i].name
			if actual_name != expected_name:
				raise TypeError(
					f"{func_name}: parameter {i} must be named "
					f"'{expected_name}', got '{actual_name}'"
				)

	# validate argument types
	if expected_arg_types is not None:
		for i, expected_type in enumerate(expected_arg_types):
			if i >= len(positional_params):
				raise TypeError(
					f"{func_name}: missing parameter at position {i} "
					f"with expected type {expected_type}"
				)

			param_name = positional_params[i].name
			actual_type = hints.get(param_name)

			if actual_type is None:
				raise TypeError(
					f"{func_name}: parameter '{param_name}' is missing type "
					f"annotation, expected {expected_type}"
				)

			if not types_compatible(actual_type, expected_type):
				raise TypeError(
					f"{func_name}: parameter '{param_name}' has type {actual_type}, "
					f"expected {expected_type}"
				)

	# validate return type
	if expected_return_type is not None:
		return_type = hints.get("return")

		if return_type is None:
			raise TypeError(
				f"{func_name}: missing return type annotation, "
				f"expected {expected_return_type}"
			)

		if not types_compatible(return_type, expected_return_type):
			raise TypeError(
				f"{func_name}: return type is {return_type}, "
				f"expected {expected_return_type}"
			)
