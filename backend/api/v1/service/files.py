"""service layer for file operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.file import File
from api.permissions import ResourceType
from api.schemas.file import FileCreate, FileUpdate
from api.settings.settings import settings
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_permission,
	require_project_access,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.typeid import TypeID


async def _get_file(file_id: TypeID, session: AsyncSession) -> File:
	"""fetch a file record by id (no access check)."""
	result = await session.execute(
		select(File).where(File.id == file_id, File.deleted_at.is_(None))
	)
	file = result.scalars().one_or_none()
	if not file:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="file not found",
		)
	return file


async def create_file(
	file_in: FileCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> File:
	"""register a new file record."""
	require_permission(principal, "files:create")
	if file_in.project_id is not None:
		await require_project_access(
			file_in.project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	data = file_in.model_dump(by_alias=True)
	data["owner_id"] = principal.user_id
	file = File(**data)
	session.add(file)
	await session.commit()
	await session.refresh(file)
	return file


async def list_files(
	session: AsyncSession,
	*,
	principal: Principal,
	project_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "created_at",
	sort_dir: SortDir = "desc",
) -> list[File]:
	"""list files accessible by the principal."""
	stmt = select(File).where(
		File.deleted_at.is_(None),
		resource_access_predicate(
			principal,
			ResourceType.FILE,
			required_level=AccessLevel.READER,
		),
	)
	if project_id is not None:
		stmt = stmt.where(File.project_id == project_id)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": File.created_at,
			"updated_at": File.updated_at,
			"filename": File.filename,
			"size_bytes": File.size_bytes,
		},
		tie_breaker=File.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def get_file(
	file_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> File:
	"""get a file by id (requires reader access)."""
	await require_resource_access(
		str(file_id),
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.READER,
	)
	return await _get_file(file_id, session)


async def update_file(
	file_id: TypeID,
	file_in: FileUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> File:
	"""update file metadata (requires editor access)."""
	await require_resource_access(
		str(file_id),
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
	)
	file = await _get_file(file_id, session)
	updates = file_in.model_dump(exclude_unset=True, by_alias=True)
	new_project_id = updates.get("project_id")
	if new_project_id is not None and str(new_project_id) != str(file.project_id or ""):
		await require_project_access(
			new_project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	for field, value in updates.items():
		setattr(file, field, value)
	await session.commit()
	await session.refresh(file)
	return file


async def delete_file(
	file_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""delete a file (soft or hard based on settings)."""
	await require_resource_access(
		str(file_id),
		session,
		principal,
		ResourceType.FILE,
		required_level=AccessLevel.EDITOR,
	)
	file = await _get_file(file_id, session)
	if settings.soft_delete.files:
		file.soft_delete()
	else:
		await session.delete(file)
	await session.commit()
