"""
dictionary utilities for nested operations.
"""

from typing import Any


def deep_merge(
	base: dict[str, Any],
	overlay: dict[str, Any],
	*,
	overwrite: bool = True,
) -> dict[str, Any]:
	"""
	recursively merge overlay into base dictionary.

	args:
        base: base dictionary
		overlay: dictionary to merge into base
		overwrite: if True, overlay values replace base values when keys collide.
			if False, existing base values are preserved and only missing keys are
			added.

	returns:
        new dictionary with merged contents

	examples:
        >>> base = {"a": {"b": 1, "c": 2}, "d": 3}
        >>> overlay = {"a": {"b": 10, "e": 4}, "f": 5}
        >>> deep_merge(base, overlay)
        {"a": {"b": 10, "c": 2, "e": 4}, "d": 3, "f": 5}
	"""
	result = base.copy()

	for key, value in overlay.items():
		if key not in result:
			result[key] = value
			continue

		base_value = result[key]

		if isinstance(base_value, dict) and isinstance(value, dict):
			result[key] = deep_merge(
				base_value,
				value,
				overwrite=overwrite,
			)
			continue

		if overwrite:
			result[key] = value

	return result


def flatten(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
	"""
	flatten a nested dictionary.

	args:
        d: dictionary to flatten
        parent_key: parent key for recursion
        sep: separator between keys

	returns:
        flattened dictionary with dotted keys

	examples:
        >>> flatten({"a": {"b": 1, "c": 2}, "d": 3})
        {"a.b": 1, "a.c": 2, "d": 3}
	"""
	items: list[tuple[str, Any]] = []

	for k, v in d.items():
		new_key = f"{parent_key}{sep}{k}" if parent_key else k
		if isinstance(v, dict):
			items.extend(flatten(v, new_key, sep=sep).items())
		else:
			items.append((new_key, v))

	return dict(items)


def unflatten(d: dict[str, Any], sep: str = ".") -> dict[str, Any]:
	"""
	unflatten a dictionary with dotted keys.

	args:
        d: flattened dictionary
        sep: separator used between keys

	returns:
        nested dictionary
	examples:
        >>> unflatten({"a.b": 1, "a.c": 2, "d": 3})
        {"a": {"b": 1, "c": 2}, "d": 3}
	"""
	result: dict[str, Any] = {}

	for key, value in d.items():
		parts = key.split(sep)
		current = result

		for part in parts[:-1]:
			if part not in current:
				current[part] = {}
			current = current[part]

		current[parts[-1]] = value

	return result
