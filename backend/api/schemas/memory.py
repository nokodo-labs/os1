"""Memory schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Base64Bytes

from api.schemas.common import MetadataModel
from nokodo_ai.utils.typeid import TypeID


class MemoryBase(MetadataModel):
	"""Shared memory fields."""

	content: str
	source_message_id: TypeID | None = None
	confidence: float | None = None
	category: str | None = None


class MemoryCreate(MemoryBase):
	"""Payload to capture a memory."""

	user_id: TypeID


class MemoryUpdate(MetadataModel):
	"""Payload to update a memory."""

	content: str | None = None
	confidence: float | None = None
	category: str | None = None


class Memory(MemoryBase):
	"""Response schema."""

	id: TypeID
	user_id: TypeID
	embedding: Base64Bytes | None = None
	last_accessed_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
