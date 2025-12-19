"""Legacy model utilities.

Prefer importing from api.models.base and api.models.mixins.
"""

from api.models.base import TYPEID_LENGTH, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	SoftDeleteMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)


__all__ = [
	"MetadataJSONMixin",
	"SoftDeleteMixin",
	"StringEnum",
	"TimestampMixin",
	"TYPEID_LENGTH",
	"TypeIDPrimaryKeyMixin",
]
