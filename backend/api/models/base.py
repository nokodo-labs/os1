"""Shared SQLAlchemy model primitives."""

from typing import Any, Final

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from nokodo_ai.utils.typeid import typeid_max_length


TYPEID_LENGTH: Final[int] = typeid_max_length()

TOOL_CALL_ID_LENGTH: Final[int] = TYPEID_LENGTH
"""bound on a tool-call identifier, wherever one is declared or stored.

one constant because an assistant message declares the id and its tool result
references it: a bound the declaration accepts and the reference rejects leaves
a tool call that can never be answered.
"""


class Base(DeclarativeBase):
	"""Base class for SQLAlchemy models."""

	pass


class StringEnum(TypeDecorator):
	"""Store Enum values as strings, returning Enum instances on read."""

	impl = String
	cache_ok = True

	def __init__(self, enum_class: type[Any], *args: Any, **kwargs: Any) -> None:
		super().__init__(*args, **kwargs)
		self.enum_class = enum_class

	def process_bind_param(self, value: Any, dialect: Any) -> str | None:
		if value is None:
			return None
		return str(value.value) if hasattr(value, "value") else str(value)

	def process_result_value(self, value: Any, dialect: Any) -> Any | None:
		if value is None:
			return None
		return self.enum_class(value)
