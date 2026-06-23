"""project routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.permissions import ResourceType
from api.schemas.project import Project as ProjectSchema
from api.schemas.project import (
	ProjectCreate,
	ProjectListFilters,
	ProjectResourceCounts,
	ProjectSearchFilters,
	ProjectSortBy,
	ProjectUpdate,
)
from api.schemas.search import Page, SearchMode
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
) -> ProjectSchema:
	"""create a new project."""
	return await project_service.create_project(
		project_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[ProjectSchema])
async def list_projects(
	filters: Annotated[ProjectListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: ProjectSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ProjectSchema]:
	"""list projects accessible by the caller."""
	return await project_service.list_projects(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_projects(
	filters: Annotated[ProjectListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count projects matching the list filters."""
	return await project_service.count_projects(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/search", response_model=Page[ProjectSchema])
async def search_projects(
	filters: Annotated[ProjectSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[ProjectSchema]:
	"""search projects accessible by the caller."""
	scored = await project_service.search_projects(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		filters=filters,
	)
	return Page(
		items=[ProjectSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.get("/{project_id}/resource_counts", response_model=ProjectResourceCounts)
async def get_project_resource_counts(
	project_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ProjectResourceCounts:
	"""fetch resource counts for a project."""
	return await project_service.get_project_resource_counts(
		project_id,
		db,
		principal=principal,
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
) -> ProjectSchema:
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
