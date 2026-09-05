"""SQLAlchemy model mixins."""

import json
from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import (
	ColumnElement,
	DateTime,
	ForeignKey,
	String,
	cast,
	func,
	literal,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
	Mapped,
	declared_attr,
	mapped_column,
)

from api.constants import PRIVATE_METADATA_KEY
from api.models.base import TYPEID_LENGTH
from nokodo_ai.types.json import JSONObject
from nokodo_ai.types.sentinels import MISSING, MissingType
from nokodo_ai.utils.typeid import TypeID, new_typeid


class TypeIDPrimaryKeyMixin:
	"""Provides a TypeID string primary key."""

	__typeid_prefix__: ClassVar[str]

	@declared_attr
	@classmethod
	def id(cls) -> Mapped[TypeID]:
		prefix = cls.__typeid_prefix__
		return mapped_column(
			String(TYPEID_LENGTH),
			primary_key=True,
			default=lambda: TypeID(new_typeid(prefix)),
		)


class OriginMessageMixin:
	"""adds the message where a resource originated."""

	@declared_attr
	@classmethod
	def origin_message_id(cls) -> Mapped[TypeID | None]:
		return mapped_column(
			String(TYPEID_LENGTH),
			ForeignKey(
				"messages.id",
				ondelete="SET NULL",
				use_alter=True,
			),
			index=True,
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
	"""Adds optional metadata column, split into a public and a private half."""

	metadata_: Mapped[JSONObject] = mapped_column(
		"metadata",  # SQLAlchemy reserves "metadata" name on DeclarativeBase
		JSONB,
		default=dict,
	)

	@classmethod
	def merge_private_metadata_sql(
		cls, values: JSONObject
	) -> ColumnElement[JSONObject]:
		"""SQL-side merge of ``values`` into the private namespace.

		the ORM equivalent is ``set_metadata(private=...)``; this exists for
		system stamping that updates rows in bulk without loading them. ``||``
		is shallow, so the namespace is merged into its own current value
		rather than replaced, and both halves survive.
		"""
		column = cls.metadata_
		patch = func.jsonb_build_object(
			PRIVATE_METADATA_KEY,
			func.coalesce(
				column[PRIVATE_METADATA_KEY],
				cast(literal("{}"), JSONB),
			).op("||")(cast(literal(json.dumps(values)), JSONB)),
		)
		return column.op("||")(patch)

	@property
	def public_metadata(self) -> JSONObject:
		"""the metadata column without the private namespace.

		named ``public_metadata`` rather than ``metadata`` because a property
		called ``metadata`` shadows the declarative ``MetaData`` registry.
		"""
		return {
			k: v for k, v in (self.metadata_ or {}).items() if k != PRIVATE_METADATA_KEY
		}

	@property
	def private_metadata(self) -> JSONObject:
		"""the private namespace, or an empty dict when absent."""
		value = (self.metadata_ or {}).get(PRIVATE_METADATA_KEY)
		return value if isinstance(value, dict) else {}

	def set_metadata(
		self,
		public: JSONObject | MissingType = MISSING,
		private: JSONObject | MissingType = MISSING,
	) -> None:
		"""replace either half of the metadata column, preserving the other.

		the only supported writer: assigning ``metadata_`` directly would
		clobber the half the caller did not mean to touch.
		"""
		merged = dict(public) if isinstance(public, dict) else self.public_metadata
		# copy on BOTH branches: the MISSING branch would otherwise alias the
		# nested dict the previous `metadata_` value still references.
		keep = (
			dict(private) if isinstance(private, dict) else dict(self.private_metadata)
		)
		if keep:
			merged[PRIVATE_METADATA_KEY] = keep
		self.metadata_ = merged


class SoftDeleteMixin:
	"""Adds soft-delete support via a nullable deleted_at timestamp."""

	deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

	@property
	def is_deleted(self) -> bool:
		return self.deleted_at is not None

	def soft_delete(self) -> None:
		self.deleted_at = datetime.now(UTC)

	def restore(self) -> None:
		self.deleted_at = None
