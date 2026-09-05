"""File schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.models.file import FileSource, FileStatus
from api.schemas.access_rule import ResourceAccessListFilters
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	PrivateFacetModel,
	PrivateInputFacetModel,
	PrivateInputModel,
	PrivateModel,
	TimestampedModel,
)
from api.schemas.sorting import CommonSortBy
from nokodo_ai.utils.typeid import TypeID


type FileSortBy = CommonSortBy | Literal["filename", "size_bytes"]
type FileCategoryFilter = Literal["image", "audio", "video", "file"]


class FileListFilters(ResourceAccessListFilters):
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


class _FilePrivateFields(BaseModel):
	"""the operator-only file columns."""

	storage_backend: str = Field(
		description="name of the storage backend holding the file bytes.",
	)
	storage_key: str = Field(
		description="key identifying the file bytes within the storage backend.",
	)
	checksum_sha256: str | None = Field(
		default=None,
		description="SHA-256 checksum of the file bytes.",
	)


class FilePrivate(_FilePrivateFields, PrivateModel):
	"""operator-only view of a file."""


class FilePrivateCreate(PrivateInputModel):
	"""operator-only fields when registering a file for existing bytes.

	only the coordinates are submitted: size and checksum are read back off the
	stored object, never taken from the caller.
	"""

	storage_backend: str = Field(
		description=_FilePrivateFields.model_fields["storage_backend"].description,
	)
	storage_key: str = Field(
		description=_FilePrivateFields.model_fields["storage_key"].description,
	)


class FilePrivateInput(PrivateInputModel):
	"""operator-only fields on a file update.

	same fields as ``_FilePrivateFields`` with every one optional: an update
	submits only what changes, so the types and defaults both differ from the
	read/create facets and cannot share the class.
	"""

	storage_backend: str | MissingType = Field(
		default=MISSING,
		description=_FilePrivateFields.model_fields["storage_backend"].description,
	)
	storage_key: str | MissingType = Field(
		default=MISSING,
		description=_FilePrivateFields.model_fields["storage_key"].description,
	)
	checksum_sha256: str | None | MissingType = Field(
		default=MISSING,
		description=_FilePrivateFields.model_fields["checksum_sha256"].description,
	)


class FileCreate(FileBase, ForbidExtraModel):
	"""payload to register a new file record.

	no ``size_bytes``: it is measured from the stored object, not declared. a
	stray flat `storage_key` (its pre-facet home) must 422, not be dropped.
	"""

	private: FilePrivateCreate


class FileUpdate(
	MetadataUpdateModel,
	ForbidExtraModel,
	PrivateInputFacetModel[FilePrivateInput],
):
	"""payload to update a file record."""

	filename: str | None | MissingType = MISSING
	description: str | None | MissingType = MISSING
	project_ids: list[TypeID] | MissingType = MISSING
	status: FileStatus | MissingType = MISSING


class File(FileBase, TimestampedModel, PrivateFacetModel[FilePrivate]):
	"""file response schema."""

	id: TypeID
	owner_id: TypeID | None = None
	source: FileSource
	size_bytes: int | None = None
	status: FileStatus
	origin_message_id: TypeID | None = None
	origin_thread_id: TypeID | None = None
	deleted_at: datetime | None = Field(default=None)
