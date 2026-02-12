"""File schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from api.models.file import FileSource, FileStatus
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class FileBase(MetadataModel):
	"""shared file fields."""

	filename: str | None = None
	mime_type: str | None = None
	project_id: TypeID | None = None


class FileCreate(FileBase):
	"""payload to register a new file record."""

	source: FileSource = FileSource.UPLOAD
	storage_backend: str
	storage_key: str
	size_bytes: int | None = None
	checksum_sha256: str | None = None


class FileUpdate(MetadataModel):
	"""payload to update a file record."""

	filename: str | None = None
	project_id: TypeID | None = None
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
