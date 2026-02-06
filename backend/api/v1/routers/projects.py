"""project routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.access_rule import AccessRule
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.v1.service import access_rules as access_rules_service
from api.v1.service.auth import Principal, get_current_principal


router = APIRouter(prefix="/projects", tags=["projects"])


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
