"""Note schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.schemas.common import MetadataModel, MetadataUpdateModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class NoteBase(MetadataModel):
	"""shared note fields."""

	title: str = Field(max_length=255)
	content: str = ""
	labels: list[str] = Field(default_factory=list)
	project_ids: list[TypeID] = []


class NoteCreate(NoteBase):
	"""payload to create a note."""

	user_id: TypeID | None = None


class NoteUpdate(MetadataUpdateModel):
	"""payload to update a note."""

	title: str | None = None
	content: str | None = None
	labels: list[str] | None = None
	project_ids: list[TypeID] | None = None


class Note(NoteBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	user_id: TypeID
	deleted_at: datetime | None = None
