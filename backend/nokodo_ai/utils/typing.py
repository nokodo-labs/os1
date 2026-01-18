import types
from typing import Annotated, Any, Literal, Union, get_args, get_origin


def extract_literal_values(type_hint: Any) -> list[Any]:
	"""
	extract literal values from any combination/nesting of:
	- Literal["a", "b"]
	- Union[Literal["a"], Literal["b"]]
	- Annotated[Literal["a"], ...]
	- or any deeper nesting of these
	"""
	origin = get_origin(type_hint)

	# base case: it's a Literal → return the values
	if origin is Literal:
		return list(get_args(type_hint))

	# Union (typing.Union or types.UnionType from `X | Y` syntax)
	if origin is Union or origin is getattr(types, "UnionType", None):
		return [v for arg in get_args(type_hint) for v in extract_literal_values(arg)]

	# Annotated → unwrap first arg (the actual type)
	if origin is Annotated:
		args = get_args(type_hint)
		return extract_literal_values(args[0]) if args else []

	raise ValueError(f"cannot extract literal values from: {type_hint}")
