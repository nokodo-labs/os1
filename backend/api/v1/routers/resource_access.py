"""shared resource access routes."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessLevelResolution,
	AccessLevelResolveRequest,
	AccessRuleCreate,
	AccessRuleResponse,
	AccessRuleUpdate,
)
from api.v1.service import access_rules as access_rules_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID, assert_typeid


ResourceIdResolver = Callable[[str], TypeID]


def _resolve_typeid(resource_type: ResourceType, value: str) -> TypeID:
	try:
		return TypeID(assert_typeid(value))
	except ValueError as exc:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		) from exc


def create_resource_access_router(
	resource_type: ResourceType,
	resource_id_param: str,
	resolve_resource_id: ResourceIdResolver | None = None,
) -> APIRouter:
	"""create access routes for one resource router."""
	router = APIRouter(prefix=f"/{{{resource_id_param}}}/access")

	def parse_resource_id(
		value: str = Path(alias=resource_id_param),
	) -> TypeID:
		if resolve_resource_id is not None:
			return resolve_resource_id(value)
		return _resolve_typeid(resource_type, value)

	@router.get("/rules", response_model=list[AccessRuleResponse])
	async def list_access_rules(
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[AccessRule]:
		"""list access rules for a resource."""
		return await access_rules_service.list_access_rules(
			resource_type, resource_id, db, principal=principal
		)

	@router.put("/rules", response_model=list[AccessRuleResponse])
	async def set_access_rules(
		rules: list[AccessRuleCreate],
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[AccessRule]:
		"""replace access rules for a resource."""
		return await access_rules_service.set_access_rules(
			resource_type,
			resource_id,
			rules,
			db,
			principal=principal,
		)

	@router.post(
		"/rules",
		response_model=AccessRuleResponse,
		status_code=status.HTTP_201_CREATED,
	)
	async def create_access_rule(
		rule: AccessRuleCreate,
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> AccessRule:
		"""create one access rule for a resource."""
		return await access_rules_service.create_access_rule(
			resource_type,
			resource_id,
			rule,
			db,
			principal=principal,
		)

	@router.post(
		"/resolve",
		response_model=list[AccessLevelResolution],
	)
	async def resolve_access_levels(
		request: AccessLevelResolveRequest,
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> list[AccessLevelResolution]:
		"""resolve effective access levels for explicit users on a resource."""
		return await access_rules_service.resolve_access_levels(
			resource_type,
			resource_id,
			request.subject_user_ids,
			db,
			principal=principal,
		)

	@router.get("/rules/{rule_id}", response_model=AccessRuleResponse)
	async def get_access_rule(
		rule_id: TypeID,
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> AccessRule:
		"""get one access rule for a resource."""
		return await access_rules_service.get_access_rule(
			resource_type,
			resource_id,
			rule_id,
			db,
			principal=principal,
		)

	@router.patch("/rules/{rule_id}", response_model=AccessRuleResponse)
	async def update_access_rule(
		rule_id: TypeID,
		update: AccessRuleUpdate,
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> AccessRule:
		"""update one access rule for a resource."""
		return await access_rules_service.update_access_rule(
			resource_type,
			resource_id,
			rule_id,
			update,
			db,
			principal=principal,
		)

	@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
	async def delete_access_rule(
		rule_id: TypeID,
		resource_id: TypeID = Depends(parse_resource_id),
		principal: Principal = Depends(get_current_principal),
		db: AsyncSession = Depends(get_db),
	) -> None:
		"""delete one access rule for a resource."""
		await access_rules_service.delete_access_rule(
			resource_type,
			resource_id,
			rule_id,
			db,
			principal=principal,
		)

	return router
