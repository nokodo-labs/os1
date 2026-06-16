"""File schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.file import FileSource, FileStatus
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type FileSortBy = CommonSortBy | Literal["filename", "size_bytes"]
type FileCategoryFilter = Literal["image", "audio", "video", "file"]


class FileListFilters(BaseModel):
	"""filters for listing files."""

	owner_id: TypeID | None = None
	project_id: TypeID | None = None
	source: FileSource | None = None
	category: FileCategoryFilter | None = None
	include_deleted: bool = False
	q: str | None = Field(default=None, min_length=1, max_length=500)


class FileSearchFilters(BaseModel):
	"""structured filters applied to file search (vector + autocomplete)."""

	owner_id: TypeID | None = None
	project_id: TypeID | None = None
	source: FileSource | None = None
	include_deleted: bool = False


class FileCounts(BaseModel):
	"""count summary for accessible files."""

	total: int = 0
	owned_total: int = 0
	shared_total: int = 0
	by_category: dict[str, int] = Field(default_factory=dict)
	by_source: dict[str, int] = Field(default_factory=dict)


class FileBase(MetadataModel):
	"""shared file fields."""

	filename: str | None = None
	mime_type: str | None = None
	description: str | None = None
	project_ids: list[TypeID] = Field(default_factory=list)


class FileCreate(FileBase):
	"""payload to register a new file record."""

	source: FileSource = FileSource.UPLOAD
	storage_backend: str
	storage_key: str
	size_bytes: int | None = None
	checksum_sha256: str | None = None


class FileUpdate(MetadataUpdateModel):
	"""payload to update a file record."""

	filename: str | None | MissingType = MISSING
	description: str | None | MissingType = MISSING
	project_ids: list[TypeID] | MissingType = MISSING
	status: FileStatus | MissingType = MISSING


class File(FileBase, TimestampedModel, ORMModel):
	"""file response schema."""

	id: TypeID
	owner_id: TypeID
	source: FileSource
	storage_backend: str
	storage_key: str
	size_bytes: int | None = None
	checksum_sha256: str | None = None
	status: FileStatus
	message_id: TypeID | None = None
	origin_thread_id: TypeID | None = None
	deleted_at: datetime | None = Field(default=None)
