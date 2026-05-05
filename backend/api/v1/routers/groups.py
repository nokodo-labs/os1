"""group management routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.group import Group, GroupMembership
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate, AccessRuleResponse
from api.schemas.group import Group as GroupSchema
from api.schemas.group import (
	GroupCreate,
	GroupListFilters,
	GroupMembershipCreate,
	GroupMembershipResponse,
	GroupSortBy,
	GroupUpdate,
)
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import groups as groups_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupSchema])
async def read_groups(
	filters: Annotated[GroupListFilters, Depends()],
	skip: int = 0,
	limit: int = 100,
	sort_by: GroupSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Group]:
	"""list groups. optionally filter by member user_id."""
	return await groups_service.list_groups(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/{group_id}", response_model=GroupSchema)
async def read_group(
	group_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Group:
	"""get a group by id."""
	return await groups_service.get_group(group_id, db, principal=principal)


@router.post("", response_model=GroupSchema, status_code=status.HTTP_201_CREATED)
async def create_group(
	group_in: GroupCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Group:
	"""create a new group. the caller becomes the owner."""
	return await groups_service.create_group(
		group_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.patch("/{group_id}", response_model=GroupSchema)
async def update_group(
	group_id: TypeID,
	body: GroupUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Group:
	"""update an existing group."""
	return await groups_service.update_group(
		group_id,
		body,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
	group_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a group."""
	await groups_service.delete_group(
		group_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


# ---- membership sub-routes ----


@router.post(
	"/{group_id}/members",
	response_model=GroupMembershipResponse,
	status_code=status.HTTP_201_CREATED,
)
async def add_member(
	group_id: TypeID,
	member_in: GroupMembershipCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> GroupMembership:
	"""add a user to a group."""
	return await groups_service.add_member(
		group_id,
		member_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete(
	"/{group_id}/members/{user_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
	group_id: TypeID,
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""remove a user from a group."""
	await groups_service.remove_member(
		group_id,
		user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


# ---- access rules sub-routes ----


@router.get(
	"/{group_id}/access-rules",
	response_model=list[AccessRuleResponse],
)
async def list_group_access_rules(
	group_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for a group."""
	return await access_rules_service.list_access_rules(
		ResourceType.GROUP, group_id, db, principal=principal
	)


@router.put(
	"/{group_id}/access-rules",
	response_model=list[AccessRuleResponse],
)
async def set_group_access_rules(
	group_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for a group."""
	return await access_rules_service.set_access_rules(
		ResourceType.GROUP, group_id, rules, db, principal=principal
	)
