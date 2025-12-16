"""Memory schemas."""

from __future__ import annotations

from datetime import datetime

from api.schemas.common import MetadataModel
from api.schemas.typeid import TypeID
from api.schemas.user import User


class MemoryBase(MetadataModel):
	"""Shared memory fields."""

	content: str
	source_message_id: TypeID | None = None
	confidence: float | None = None
	category: str | None = None


class MemoryCreate(MemoryBase):
	"""Payload to capture a memory."""

	user_id: TypeID


class Memory(MemoryBase):
	"""Response schema."""

	id: TypeID
	user_id: TypeID
	embedding: bytes | None = None
	last_accessed_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
	owner: User | None = None
