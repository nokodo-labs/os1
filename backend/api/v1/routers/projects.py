"""project routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.access_rule import AccessRule
from api.models.project import Project
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.schemas.project import Project as ProjectSchema
from api.schemas.project import ProjectCreate, ProjectUpdate
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import projects as project_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_project(
	project_in: ProjectCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Project:
	"""create a new project."""
	return await project_service.create_project(project_in, db, principal=principal)


@router.get("", response_model=list[ProjectSchema])
async def list_projects(
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "updated_at",
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
) -> Project:
	"""fetch a project by id."""
	return await project_service.get_project(project_id, db, principal=principal)


@router.patch("/{project_id}", response_model=ProjectSchema)
async def update_project(
	project_id: TypeID,
	project_in: ProjectUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Project:
	"""update a project."""
	return await project_service.update_project(
		project_id, project_in, db, principal=principal
	)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
	project_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a project."""
	await project_service.delete_project(project_id, db, principal=principal)


# ---- access rules ----


@router.get("/{project_id}/access-rules", response_model=list[AccessRuleResponse])
async def list_project_access_rules(
	project_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for a project."""
	return await access_rules_service.list_access_rules(
		ResourceType.PROJECT, project_id, db, principal=principal
	)


@router.put("/{project_id}/access-rules", response_model=list[AccessRuleResponse])
async def set_project_access_rules(
	project_id: str,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for a project."""
	return await access_rules_service.set_access_rules(
		ResourceType.PROJECT,
		project_id,
		rules,
		db,
		principal=principal,
	)
