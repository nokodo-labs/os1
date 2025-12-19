"""SQLAlchemy model mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from api.models.base import TYPEID_LENGTH
from nokodo_ai.utils.typeid import new_typeid


class TypeIDPrimaryKeyMixin:
	"""Provides a TypeID string primary key."""

	__typeid_prefix__: ClassVar[str]

	@declared_attr.directive
	def id(self) -> Mapped[str]:
		return mapped_column(
			String(TYPEID_LENGTH),
			primary_key=True,
			default=lambda: new_typeid(self.__typeid_prefix__),
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


class SoftDeleteMixin:
	"""Adds soft-delete support via a nullable deleted_at timestamp."""

	deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	@property
	def is_deleted(self) -> bool:
		return self.deleted_at is not None

	def soft_delete(self) -> None:
		self.deleted_at = datetime.now(UTC)
