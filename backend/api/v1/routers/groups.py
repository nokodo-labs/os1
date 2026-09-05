"""group management routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.group import Group, GroupMembership
from api.permissions import ResourceType
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
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.events import SessionId
from api.v1.service.groups import (
	add_member as add_member_service,
)
from api.v1.service.groups import (
	count_groups as count_groups_service,
)
from api.v1.service.groups import (
	create_group as create_group_service,
)
from api.v1.service.groups import (
	delete_group as delete_group_service,
)
from api.v1.service.groups import (
	get_group,
	list_groups,
)
from api.v1.service.groups import (
	remove_member as remove_member_service,
)
from api.v1.service.groups import (
	update_group as update_group_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/groups", tags=["groups"])
router.include_router(create_resource_access_router(ResourceType.GROUP, "group_id"))


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
	return await list_groups(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_groups(
	filters: Annotated[GroupListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count groups matching the list filters."""
	return await count_groups_service(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/{group_id}", response_model=GroupSchema)
async def read_group(
	group_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Group:
	"""get a group by id."""
	return await get_group(group_id, db, principal=principal)


@router.post("", response_model=GroupSchema, status_code=status.HTTP_201_CREATED)
async def create_group(
	group_in: GroupCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Group:
	"""create a new group. the caller becomes the owner."""
	return await create_group_service(
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
	return await update_group_service(
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
	await delete_group_service(
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
	return await add_member_service(
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
	await remove_member_service(
		group_id,
		user_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
