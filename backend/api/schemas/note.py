"""Note schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import MetadataModel
from nokodo_ai.utils.typeid import TypeID


class NoteBase(MetadataModel):
	"""shared note fields."""

	title: str = Field(max_length=255)
	content: str = ""
	labels: list[str] = Field(default_factory=list)


class NoteCreate(NoteBase):
	"""payload to create a note."""

	user_id: TypeID | None = None


class NoteUpdate(MetadataModel):
	"""payload to update a note."""

	title: str | None = None
	content: str | None = None
	labels: list[str] | None = None


class Note(NoteBase):
	"""response schema."""

	id: TypeID
	user_id: TypeID
	deleted_at: datetime | None = None
	created_at: datetime
	updated_at: datetime
