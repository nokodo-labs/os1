"""memory schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Base64Bytes, BaseModel, Field

from api.schemas.common import MetadataModel, MetadataUpdateModel, TimestampedModel
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type MemorySortBy = (
	CommonSortBy
	| Literal[
		"category",
		"content_length",
		"last_accessed_at",
		"confidence",
	]
)


class MemoryListFilters(BaseModel):
	"""filters for listing memories."""

	user_id: TypeID
	search: str | None = Field(default=None, min_length=1, max_length=500)


class MemoryBase(MetadataModel):
	"""shared memory fields."""

	content: str
	source_message_id: TypeID | None = None
	confidence: float | None = None
	category: str | None = None


class MemoryCreate(MemoryBase):
	"""payload to capture a memory."""

	user_id: TypeID


class MemoryUpdate(MetadataUpdateModel):
	"""payload to update a memory."""

	content: str | None = None
	confidence: float | None = None
	category: str | None = None


class Memory(MemoryBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	user_id: TypeID
	embedding: Base64Bytes | None = None
	last_accessed_at: datetime | None = None
