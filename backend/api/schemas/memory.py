"""memory schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Base64Bytes

from api.schemas.common import MetadataModel, MetadataUpdateModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


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
