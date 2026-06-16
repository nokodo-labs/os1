"""file management routers."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.models.file import File, FileSource
from api.permissions import ResourceType
from api.schemas.file import File as FileSchema
from api.schemas.file import (
	FileCounts,
	FileCreate,
	FileListFilters,
	FileSearchFilters,
	FileSortBy,
	FileUpdate,
)
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service import files as file_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin, require_resource_access
from api.v1.service.events import SessionId
from api.v1.tasks.files import run_file_maintenance_backfill_sweep
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


# media types that browsers can render inline (images, audio, video, pdf)
_INLINE_PREFIXES = ("image/", "audio/", "video/", "application/pdf")


def _is_inline_type(content_type: str | None) -> bool:
	"""return True if the content type should be served inline."""
	if not content_type:
		return False
	return any(content_type.startswith(p) for p in _INLINE_PREFIXES)


router = APIRouter(prefix="/files", tags=["files"])
router.include_router(create_resource_access_router(ResourceType.FILE, "file_id"))


@router.post("", response_model=FileSchema, status_code=status.HTTP_201_CREATED)
async def create_file(
	file_in: FileCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""register a new file record (metadata only)."""
	return await file_service.register_stored_file(
		file_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post(
	"/upload",
	response_model=FileSchema,
	status_code=status.HTTP_201_CREATED,
)
async def upload_file(
	file: UploadFile,
	project_ids: list[TypeID] = Form(default=[]),
	source: FileSource = Form(default=FileSource.UPLOAD),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""upload a file (multipart) and create the record."""
	return await file_service.upload_file(
		file,
		db,
		principal=principal,
		project_ids=project_ids,
		source=source,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[FileSchema])
async def list_files(
	filters: Annotated[FileListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: FileSortBy = "created_at",
	sort_dir: SortDir = "desc",
	resolve_origin: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[File]:
	"""list files accessible by the caller."""
	return await file_service.list_files(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		resolve_origin=resolve_origin,
	)


@router.get("/count", response_model=FileCounts)
async def count_files(
	filters: Annotated[FileListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> FileCounts:
	"""count files accessible by the caller."""
	return await file_service.count_files(db, principal=principal, filters=filters)


@router.get("/search", response_model=Page[FileSchema])
async def search_files(
	filters: Annotated[FileSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[FileSchema]:
	"""search files returning ranked file objects."""
	scored = await file_service.search_files(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[FileSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.post("/revectorize")
async def revectorize_files(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all described files into qdrant. admin only."""
	require_admin(principal)
	count = await file_service.vectorize_all_files(db)
	return {"vectorized": count}


@router.post("/maintenance-backfill/run")
async def run_file_maintenance_backfill(
	batch_size: Annotated[int | None, Query(ge=1, le=200)] = None,
	principal: Principal = Depends(get_current_principal),
) -> JSONObject:
	"""manually run one batch of the retroactive file maintenance sweep.

	admin-only. this intentionally ignores the scheduled maintenance enabled
	flag so admins can spot-check the sweep (currently description backfill for
	imported files) without leaving the periodic schedule on.
	"""
	require_admin(principal)
	return await run_file_maintenance_backfill_sweep(
		batch_size=batch_size,
		respect_enabled=False,
	)


@router.post("/{file_id}/maintenance/run", response_model=FileSchema)
async def run_file_maintenance(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> File:
	"""regenerate description and re-vectorize a single file.

	caller must have admin-level access on the file (owner or higher). runs
	the description and vectorization pipeline synchronously and returns the
	updated file record.
	"""
	await require_resource_access(
		file_id,
		db,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.ADMIN,
	)
	await file_service.process_file_description(file_id)
	return await file_service.get_file(file_id, db, principal=principal)


@router.get("/{file_id}", response_model=FileSchema)
async def get_file(
	file_id: TypeID,
	resolve_origin: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> FileSchema:
	"""fetch a file by id."""
	return await file_service.get_file_payload(
		file_id,
		db,
		principal=principal,
		resolve_origin=resolve_origin,
	)


@router.get("/{file_id}/content")
async def get_file_content(
	file_id: TypeID,
	download: bool = Query(
		default=False,
		description="force browser download instead of inline display",
	),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""download file content."""
	stream, content_type, filename, size_bytes = await file_service.get_file_content(
		file_id, db, principal=principal
	)
	headers: dict[str, str] = {}
	if filename:
		encoded = quote(filename, safe="")
		fallback = filename.encode("ascii", "ignore").decode("ascii") or "download"
		fallback = fallback.replace("\\", "_").replace('"', "_")
		# use inline disposition for media types so browsers render them
		# directly (e.g. <img> tags); attachment for everything else.
		# download=True forces attachment regardless of content type.
		if download:
			disposition = "attachment"
		else:
			disposition = "inline" if _is_inline_type(content_type) else "attachment"
		headers["Content-Disposition"] = (
			f"{disposition}; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"
		)
	if size_bytes is not None:
		headers["Content-Length"] = str(size_bytes)
	return StreamingResponse(
		stream,
		media_type=content_type or "application/octet-stream",
		headers=headers,
	)


@router.get("/{file_id}/preview")
async def get_file_preview(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
	"""temporary proxy for file content previews."""
	return await get_file_content(
		file_id,
		download=False,
		principal=principal,
		db=db,
	)


@router.get("/{file_id}/url")
async def get_file_url(
	file_id: TypeID,
	expires_in: int | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, str | None]:
	"""get a direct or presigned URL for the file."""
	url = await file_service.get_file_url(
		file_id, db, principal=principal, expires_in=expires_in
	)
	return {"url": url}


@router.patch("/{file_id}", response_model=FileSchema)
async def update_file(
	file_id: TypeID,
	file_in: FileUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""update file metadata."""
	return await file_service.update_file(
		file_id,
		file_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
	file_id: TypeID,
	permanent: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a file."""
	await file_service.delete_file(
		file_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
		permanent=permanent,
	)


@router.post("/{file_id}/restore", response_model=FileSchema)
async def restore_file(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""restore a soft-deleted file. admin only."""
	return await file_service.restore_file(
		file_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
