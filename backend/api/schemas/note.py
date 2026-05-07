"""Note schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type NoteSortBy = CommonSortBy | Literal["title"]


class NoteListFilters(BaseModel):
	"""filters for listing notes."""

	user_id: TypeID | None = None
	labels: list[str] | None = None


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

	title: str | MissingType = MISSING
	content: str | MissingType = MISSING
	labels: list[str] | MissingType = MISSING
	project_ids: list[TypeID] | MissingType = MISSING


class Note(NoteBase, TimestampedModel):
	"""response schema."""

	id: TypeID
	user_id: TypeID
	deleted_at: datetime | None = None
