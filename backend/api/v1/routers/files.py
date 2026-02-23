"""file management routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.file import File
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate, AccessRuleResponse
from api.schemas.file import File as FileSchema
from api.schemas.file import FileCreate, FileUpdate
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import files as file_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileSchema, status_code=status.HTTP_201_CREATED)
async def create_file(
	file_in: FileCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> File:
	"""register a new file record."""
	return await file_service.create_file(
		file_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[FileSchema])
async def list_files(
	project_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "created_at",
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
		ResourceType.FILE, str(file_id), db, principal=principal
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
		str(file_id),
		rules,
		db,
		principal=principal,
	)
