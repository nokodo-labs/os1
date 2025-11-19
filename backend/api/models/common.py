"""Common SQLAlchemy model utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


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
