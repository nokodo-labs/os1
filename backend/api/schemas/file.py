"""File schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.file import FileSource, FileStatus
from api.schemas.common import (
	MetadataModel,
	MetadataUpdateModel,
	ORMModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type FileSortBy = CommonSortBy | Literal["filename", "size_bytes"]


class FileListFilters(BaseModel):
	"""filters for listing files."""

	project_id: TypeID | None = None


class FileBase(MetadataModel):
	"""shared file fields."""

	filename: str | None = None
	mime_type: str | None = None
	project_ids: list[TypeID] = []


class FileCreate(FileBase):
	"""payload to register a new file record."""

	source: FileSource = FileSource.UPLOAD
	storage_backend: str
	storage_key: str
	size_bytes: int | None = None
	checksum_sha256: str | None = None


class FileUpdate(MetadataUpdateModel):
	"""payload to update a file record."""

	filename: str | None = None
	project_ids: list[TypeID] | None = None
	status: FileStatus | None = None


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
	deleted_at: datetime | None = Field(default=None)
