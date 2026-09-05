"""search utility helpers."""


def contains_pattern(value: str) -> str:
	"""build an escaped LIKE contains pattern."""
	escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"
