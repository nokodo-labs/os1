"""file management routers."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.file import File, FileSource
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.schemas.file import File as FileSchema
from api.schemas.file import FileCreate, FileSortBy, FileUpdate
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import files as file_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


# media types that browsers can render inline (images, audio, video, pdf)
_INLINE_PREFIXES = ("image/", "audio/", "video/", "application/pdf")


def _is_inline_type(content_type: str | None) -> bool:
	"""return True if the content type should be served inline."""
	if not content_type:
		return False
	return any(content_type.startswith(p) for p in _INLINE_PREFIXES)


router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileSchema, status_code=status.HTTP_201_CREATED)
async def create_file(
	file_in: FileCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""register a new file record (metadata only)."""
	return await file_service.create_file(
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
	project_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: FileSortBy = "created_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[File]:
	"""list files accessible by the caller."""
	return await file_service.list_files(
		db,
		principal=principal,
		project_id=project_id,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/{file_id}", response_model=FileSchema)
async def get_file(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> File:
	"""fetch a file by id."""
	return await file_service.get_file(file_id, db, principal=principal)


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
		# use inline disposition for media types so browsers render them
		# directly (e.g. <img> tags); attachment for everything else.
		# download=True forces attachment regardless of content type.
		if download:
			disposition = "attachment"
		else:
			disposition = "inline" if _is_inline_type(content_type) else "attachment"
		headers["Content-Disposition"] = (
			f"{disposition}; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
		)
	if size_bytes is not None:
		headers["Content-Length"] = str(size_bytes)
	return StreamingResponse(
		stream,
		media_type=content_type or "application/octet-stream",
		headers=headers,
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
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""soft-delete a file."""
	await file_service.delete_file(
		file_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


# ---- access rules ----


@router.get("/{file_id}/access-rules", response_model=list[AccessRuleResponse])
async def list_file_access_rules(
	file_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for a file."""
	return await access_rules_service.list_access_rules(
		ResourceType.FILE, file_id, db, principal=principal
	)


@router.put("/{file_id}/access-rules", response_model=list[AccessRuleResponse])
async def set_file_access_rules(
	file_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for a file."""
	return await access_rules_service.set_access_rules(
		ResourceType.FILE,
		file_id,
		rules,
		db,
		principal=principal,
	)
