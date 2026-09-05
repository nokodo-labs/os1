"""memory schemas."""

from base64 import b64encode
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from api.schemas.access_rule import ResourceAccessListFilters
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	PrivateFacetModel,
	PrivateModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type MemorySortBy = (
	CommonSortBy
	| Literal[
		"tags",
		"content_length",
		"last_accessed_at",
		"confidence",
	]
)


class MemoryListFilters(ResourceAccessListFilters):
	"""filters for listing memories."""

	owner_id: TypeID | None = None
	search: str | None = Field(default=None, min_length=1, max_length=500)
	tags: list[str] | None = None


class MemorySearchFilters(BaseModel):
	"""structured filters applied to memory search (vector + autocomplete)."""

	owner_id: TypeID | None = None
	tags: list[str] | None = None


class MemoryBase(MetadataModel):
	"""shared memory fields."""

	content: str
	source_message_id: TypeID | None = None
	confidence: float | None = None
	tags: list[str] | None = None


class MemoryCreate(MemoryBase, ForbidExtraModel):
	"""payload to capture a memory."""

	user_id: TypeID


class MemoryUpdate(MetadataUpdateModel):
	"""payload to update a memory."""

	content: str | MissingType = MISSING
	confidence: float | None | MissingType = MISSING
	tags: list[str] | None | MissingType = MISSING


class MemoryPrivate(PrivateModel):
	"""operator-only view of a memory: its embedding and private metadata."""

	embedding: bytes | None = Field(
		default=None,
		description="raw embedding vector bytes for the memory content.",
	)

	@field_serializer("embedding", when_used="json")
	def _embedding_base64(self, value: bytes | None) -> str | None:
		# the column holds raw vector bytes; Base64Bytes would DECODE them on
		# validation and fail. raw in, base64 out.
		return b64encode(value).decode() if value is not None else None


class Memory(MemoryBase, TimestampedModel, PrivateFacetModel[MemoryPrivate]):
	"""response schema."""

	id: TypeID
	user_id: TypeID
	last_accessed_at: datetime | None = None
