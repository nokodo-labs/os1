"""search utility helpers."""

from __future__ import annotations


def contains_pattern(value: str) -> str:
	"""build an escaped LIKE contains pattern."""
	escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"
