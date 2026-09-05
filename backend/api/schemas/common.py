"""shared schema utilities."""

from datetime import datetime
from typing import Self, cast, get_args, overload

from pydantic import (
	BaseModel,
	ConfigDict,
	Field,
	field_validator,
	model_validator,
)
from pydantic.annotated_handlers import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from api.constants import PRIVATE_METADATA_KEY
from nokodo_ai.types.json import JSONObject
from nokodo_ai.types.sentinels import MISSING, MissingType


class ORMModel(BaseModel):
	"""base schema with ORM compatibility."""

	model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ForbidExtraModel(ORMModel):
	"""base for wire-bound write schemas: an unknown field is a 422."""

	model_config = ConfigDict(extra="forbid")


@overload
def unwrap_missing[T](value: T | MissingType) -> T | None: ...


@overload
def unwrap_missing[T](value: T | MissingType, default: T) -> T: ...


def unwrap_missing[T](value: T | MissingType, default: T | None = None) -> T | None:
	"""resolve an optional field to its value, or ``default`` when unset."""
	if value is MISSING:
		return default
	return cast("T", value)


def _reject_reserved_key(value: object) -> object:
	"""refuse a public metadata payload that addresses the private namespace."""
	if isinstance(value, dict) and PRIVATE_METADATA_KEY in value:
		raise ValueError(
			f"{PRIVATE_METADATA_KEY!r} is reserved; write private metadata "
			"through the private facet"
		)
	return value


ROW_METADATA_ALIASES = ("public_metadata", "private_metadata")
"""ORM accessor names the metadata field validates from; never wire names."""


class _RowAliasedMetadataModel(ORMModel):
	"""renames the row-reading metadata alias back to ``metadata`` in OpenAPI.

	subclass this instead of ``ORMModel`` for any schema whose metadata field
	validates from a differently-named ORM accessor.
	"""

	@classmethod
	def __get_pydantic_json_schema__(
		cls,
		core_schema: CoreSchema,
		handler: GetJsonSchemaHandler,
	) -> JsonSchemaValue:
		schema = handler(core_schema)
		properties = schema.get("properties")
		required = schema.get("required")
		if isinstance(properties, dict):
			for alias in ROW_METADATA_ALIASES:
				if alias in properties:
					properties["metadata"] = properties.pop(alias)
					if isinstance(required, list) and alias in required:
						required[required.index(alias)] = "metadata"
		return schema

	@model_validator(mode="before")
	@classmethod
	def _reject_row_alias_from_the_wire(cls, data: object) -> object:
		"""a request body must use ``metadata``, never the ORM accessor name.

		``populate_by_name`` makes the alias a second accepted key, which would
		put an internal name on the public contract. only dict input can come
		from a client; an ORM row arrives as an object.
		"""
		if isinstance(data, dict):
			for alias in ROW_METADATA_ALIASES:
				if alias in data:
					raise ValueError(f"unknown field: {alias!r}")
		return data


class MetadataModel(_RowAliasedMetadataModel):
	"""public metadata for schemas backed by MetadataJSONMixin.

	read and write schemas share this, so it takes no position on unknown
	fields: a write schema states its own strictness via ``ForbidExtraModel``.
	"""

	metadata: JSONObject = Field(
		default_factory=dict,
		validation_alias="public_metadata",
	)

	@field_validator("metadata", mode="before")
	@classmethod
	def _validate_metadata(cls, value: object) -> object:
		if value is None:
			return {}
		return _reject_reserved_key(value)


class PrivateModel(_RowAliasedMetadataModel):
	"""base for a resource's ``private`` facet: data non-operators never see."""

	metadata: JSONObject = Field(
		default_factory=dict,
		validation_alias="private_metadata",
	)

	@field_validator("metadata", mode="before")
	@classmethod
	def _coerce_none_metadata(cls, value: object) -> object:
		if value is None:
			return {}
		return value


class MetadataUpdateModel(ORMModel):
	"""adds public metadata support for update schemas."""

	model_config = ConfigDict(extra="forbid")

	metadata: JSONObject | MissingType = MISSING

	@field_validator("metadata", mode="before")
	@classmethod
	def _validate_metadata(cls, value: object) -> object:
		return _reject_reserved_key(value)


class PrivateFacetModel[PrivateT: PrivateModel](ORMModel):
	"""a response schema whose operator-only data lives in ``private``.

	parametrize with the resource's facet -
	``File(PrivateFacetModel[FilePrivate])`` - and never redeclare the field.
	``from_row`` is the only thing that populates the facet.

	never embed one of these in another schema: ``project_private`` only
	reaches the top level, so a nested facet would reach whoever receives the
	outer payload. embed the id instead.
	"""

	private: PrivateT | None = None

	@classmethod
	def _private_model(cls) -> type[PrivateModel]:
		"""the facet type this schema was parametrized with."""
		for arg in get_args(cls.model_fields["private"].annotation):
			if isinstance(arg, type) and issubclass(arg, PrivateModel):
				return arg
		raise TypeError(f"{cls.__name__} declares no private facet type")

	@classmethod
	def from_row(cls, row: object) -> Self:
		"""build the full payload for an ORM row, private facet populated.

		principal-neutral, so it must not reach a client directly: pass it
		through ``project_private`` first.
		"""
		return cls.model_validate(row).model_copy(
			update={"private": cls._private_model().model_validate(row)}
		)


class PrivateInputModel(ForbidExtraModel):
	"""base for the write side of a resource's ``private`` facet."""

	metadata: JSONObject | MissingType = MISSING


class PrivateInputFacetModel[PrivateInputT: PrivateInputModel](ORMModel):
	"""a write schema whose operator-only fields live in ``private``.

	the write-side mirror of ``PrivateFacetModel``. ``MISSING`` means the facet
	was not submitted; services gate a submitted one through
	``require_private_write``.
	"""

	model_config = ConfigDict(extra="forbid")

	private: PrivateInputT | MissingType = MISSING


class TimestampedModel(ORMModel):
	"""adds standard timestamp fields."""

	created_at: datetime
	updated_at: datetime
