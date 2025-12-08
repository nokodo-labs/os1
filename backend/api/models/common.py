"""Common SQLAlchemy model utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class StringEnum(TypeDecorator):
	"""
	Enables passing a Python Enum class to a SQLAlchemy column,
	storing the Enum member's *value* (string) in the database,
	and returning the Enum member (object) when querying.
	"""

	impl = String
	cache_ok = True

	def __init__(self, enum_class: type[Any], *args: Any, **kwargs: Any) -> None:
		super().__init__(*args, **kwargs)
		self.enum_class = enum_class

	def process_bind_param(self, value: Any, dialect: Any) -> str | None:
		if value is None:
			return None
		return value.value if hasattr(value, "value") else value

	def process_result_value(self, value: Any, dialect: Any) -> Any | None:
		if value is None:
			return None
		return self.enum_class(value)


class UUIDPrimaryKeyMixin:
	"""Provides a string-based UUID primary key."""

	id: Mapped[str] = mapped_column(
		String(36),
		primary_key=True,
		default=lambda: str(uuid4()),
	)


class TimestampMixin:
	"""Adds created/updated timestamps."""

	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
		onupdate=func.now(),
	)


class MetadataJSONMixin:
	"""Adds optional metadata column."""

	metadata_: Mapped[dict[str, Any]] = mapped_column(
		"metadata",  # SQLAlchemy reserves "metadata" name on DeclarativeBase
		JSON,
		default=dict,
	)
