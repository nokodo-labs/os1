"""file management routers."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessLevel
from api.permissions import ActionPermission, ResourceType
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
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_permission, require_resource_access
from api.v1.service.events import SessionId
from api.v1.service.files import (
	count_files as count_files_service,
)
from api.v1.service.files import (
	delete_file as delete_file_service,
)
from api.v1.service.files import (
	file_payloads,
	get_file_payload,
	process_file_description,
	register_stored_file,
	vectorize_files,
)
from api.v1.service.files import (
	get_file_content as get_file_content_service,
)
from api.v1.service.files import (
	get_file_url as get_file_url_service,
)
from api.v1.service.files import (
	list_files as list_files_service,
)
from api.v1.service.files import (
	restore_file as restore_file_service,
)
from api.v1.service.files import (
	search_files as search_files_service,
)
from api.v1.service.files import (
	update_file as update_file_service,
)
from api.v1.service.files import (
	upload_file as upload_file_service,
)
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
) -> FileSchema:
	"""register a new file record (metadata only)."""
	file = await register_stored_file(
		file_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return file_payloads([file], principal)[0]


@router.post(
	"/upload",
	response_model=FileSchema,
	status_code=status.HTTP_201_CREATED,
)
async def upload_file(
	file: UploadFile,
	project_ids: list[TypeID] = Form(default=[]),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> FileSchema:
	"""upload a file (multipart) and create the record."""
	stored = await upload_file_service(
		file,
		db,
		principal=principal,
		project_ids=project_ids,
		origin_session_id=x_session_id,
	)
	return file_payloads([stored], principal)[0]


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
) -> list[FileSchema]:
	"""list files accessible by the caller."""
	files = await list_files_service(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		resolve_origin=resolve_origin,
	)
	return file_payloads(files, principal)


@router.get("/count", response_model=FileCounts)
async def count_files(
	filters: Annotated[FileListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> FileCounts:
	"""count files accessible by the caller."""
	return await count_files_service(db, principal=principal, filters=filters)


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
	scored = await search_files_service(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=file_payloads([hit.item for hit in scored[:limit]], principal),
		has_more=len(scored) > limit,
	)


@router.post("/revectorize")
async def revectorize_files(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all described files into qdrant. files operators only."""
	require_permission(principal, ActionPermission.FILES_MANAGE)
	count = await vectorize_files(db)
	return {"vectorized": count}


@router.post("/maintenance-backfill/run")
async def run_file_maintenance_backfill(
	batch_size: Annotated[int | None, Query(ge=1, le=200)] = None,
	principal: Principal = Depends(get_current_principal),
) -> JSONObject:
	"""manually run one batch of the retroactive file maintenance sweep.

	files operators only. this intentionally ignores the scheduled maintenance
	enabled flag so operators can spot-check the sweep (deferred content
	vectorization and description backfill) without leaving the schedule on.
	"""
	require_permission(principal, ActionPermission.FILES_MANAGE)
	return await run_file_maintenance_backfill_sweep(
		batch_size=batch_size,
		respect_enabled=False,
	)


@router.post("/{file_id}/maintenance/run", response_model=FileSchema)
async def run_file_maintenance(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> FileSchema:
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
	await process_file_description(file_id)
	return await get_file_payload(
		file_id,
		db,
		principal=principal,
		use_cache=False,
	)


@router.get("/{file_id}", response_model=FileSchema)
async def get_file(
	file_id: TypeID,
	resolve_origin: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> FileSchema:
	"""fetch a file by id."""
	return await get_file_payload(
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
	stream, content_type, filename, size_bytes = await get_file_content_service(
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
	url = await get_file_url_service(
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
) -> FileSchema:
	"""update file metadata."""
	file = await update_file_service(
		file_id,
		file_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return file_payloads([file], principal)[0]


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
	file_id: TypeID,
	permanent: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a file."""
	await delete_file_service(
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
) -> FileSchema:
	"""restore a soft-deleted file. admin only."""
	file = await restore_file_service(
		file_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return file_payloads([file], principal)[0]
