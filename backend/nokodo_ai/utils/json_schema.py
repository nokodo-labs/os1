from collections.abc import Callable
from inspect import Parameter, signature
from typing import Any, get_type_hints

from pydantic import create_model

from ..types.json import JSONObject


def schema_from_callable(
	func: Callable[..., Any],
	skip_self: bool = True,
	skip_fields: set[str] | None = None,
	skip_dunder: bool = True,
) -> JSONObject:
	"""generate JSON Schema from a callable's signature.

	skips `self` and any `__*__` parameters (context injection).
	"""
	hints = get_type_hints(func)
	sig = signature(func)

	fields: dict[str, Any] = {}

	for name, param in sig.parameters.items():
		# skip self
		if skip_self and name == "self":
			continue

		# skip fields in skip_fields set
		if skip_fields and name in skip_fields:
			continue

		# skip __dunder__ context params
		if skip_dunder and name.startswith("__") and name.endswith("__"):
			continue

		# skip **kwargs / *args
		if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
			continue

		type_hint = hints.get(name, Any)

		if param.default is Parameter.empty:
			fields[name] = (type_hint, ...)  # required
		else:
			fields[name] = (type_hint, param.default)  # optional

	if not fields:
		return {}

	dynamic_model = create_model(f"{func.__name__}_params", **fields)
	return dynamic_model.model_json_schema()
