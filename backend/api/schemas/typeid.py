"""Pydantic TypeID type.

This provides runtime validation for TypeID strings and keeps OpenAPI output
consistent across the backend.
"""

from __future__ import annotations

from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from nokodo_ai.utils import typeid


class TypeID(str):
	"""Validated TypeID string."""

	@classmethod
	def __get_pydantic_core_schema__(
		cls,
		source_type: Any,
		handler: GetCoreSchemaHandler,
	) -> core_schema.CoreSchema:
		return core_schema.no_info_after_validator_function(
			cls._validate,
			core_schema.str_schema(max_length=typeid.typeid_max_length()),
		)

	@classmethod
	def __get_pydantic_json_schema__(
		cls,
		core_schema: core_schema.CoreSchema,
		handler: Any,
	) -> JsonSchemaValue:
		schema = handler(core_schema)
		schema.update(
			{
				"pattern": (
					r"^(?:[a-z](?:[a-z_]{0,61}[a-z])?_)?"
					r"[0-7][0123456789abcdefghjkmnpqrstvwxyz]{25}$"
				),
				"examples": ["user_01h5fskfsk4fpeqwnsyz5hj55t"],
			}
		)
		return schema

	@classmethod
	def _validate(cls, value: str) -> TypeID:
		if not typeid.is_typeid(value):
			raise ValueError("invalid typeid")
		return cls(value)
