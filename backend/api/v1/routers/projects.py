"""project routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.acl import AccessControlEntry
from api.schemas.acl import AccessControlEntry as AccessControlEntrySchema
from api.schemas.acl import AccessControlEntryCreate
from api.v1.service import acl as acl_service


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/acl", response_model=list[AccessControlEntrySchema])
async def list_project_acl(
	project_id: str,
	db: AsyncSession = Depends(get_db),
) -> list[AccessControlEntry]:
	"""List acl entries for a project."""
	return await acl_service.list_project_acl(project_id, db)


@router.put("/{project_id}/acl", response_model=list[AccessControlEntrySchema])
async def set_project_acl(
	project_id: str,
	entries: list[AccessControlEntryCreate],
	db: AsyncSession = Depends(get_db),
) -> list[AccessControlEntry]:
	"""Replace acl entries for a project."""
	return await acl_service.set_project_acl(project_id, entries, db)
