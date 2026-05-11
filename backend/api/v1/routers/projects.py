"""project routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.project import Project
from api.permissions import ResourceType
from api.schemas.project import Project as ProjectSchema
from api.schemas.project import ProjectCreate, ProjectSortBy, ProjectUpdate
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service import projects as project_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/projects", tags=["projects"])
router.include_router(create_resource_access_router(ResourceType.PROJECT, "project_id"))


@router.post("", response_model=ProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_project(
	project_in: ProjectCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Project:
	"""create a new project."""
	return await project_service.create_project(
		project_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[ProjectSchema])
async def list_projects(
	skip: int = 0,
	limit: int = 50,
	sort_by: ProjectSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Project]:
	"""list projects accessible by the caller."""
	return await project_service.list_projects(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/{project_id}", response_model=ProjectSchema)
async def get_project(
	project_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ProjectSchema:
	"""fetch a project by id."""
	return await project_service.get_project_payload(
		project_id, db, principal=principal
	)


@router.patch("/{project_id}", response_model=ProjectSchema)
async def update_project(
	project_id: TypeID,
	project_in: ProjectUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Project:
	"""update a project."""
	return await project_service.update_project(
		project_id,
		project_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a project."""
	await project_service.delete_project(
		project_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
