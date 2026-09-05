"""role management routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.role import Role
from api.models.user import User
from api.schemas.role import Role as RoleSchema
from api.schemas.role import RoleCreate, RoleListFilters, RoleSortBy, RoleUpdate
from api.schemas.sorting import SortDir
from api.schemas.user import User as UserSchema
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.roles import (
	count_roles as count_roles_service,
)
from api.v1.service.roles import (
	create_role as create_role_service,
)
from api.v1.service.roles import (
	delete_role as delete_role_service,
)
from api.v1.service.roles import (
	get_role,
	list_role_members,
	list_roles,
)
from api.v1.service.roles import (
	set_role_members as set_role_members_service,
)
from api.v1.service.roles import (
	update_role as update_role_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleSchema])
async def read_roles(
	filters: Annotated[RoleListFilters, Depends()],
	skip: int = 0,
	limit: int = 100,
	sort_by: RoleSortBy = "priority",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Role]:
	"""list all roles. optionally filter by user_id."""
	return await list_roles(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_roles(
	filters: Annotated[RoleListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count roles matching the list filters."""
	return await count_roles_service(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/{role_id}", response_model=RoleSchema)
async def read_role(
	role_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""get a role by id."""
	return await get_role(role_id, db, principal=principal)


@router.post("", response_model=RoleSchema, status_code=status.HTTP_201_CREATED)
async def create_role(
	role_in: RoleCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""create a new role."""
	return await create_role_service(role_in, db, principal=principal)


@router.patch("/{role_id}", response_model=RoleSchema)
async def update_role(
	role_id: TypeID,
	body: RoleUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""update an existing role."""
	return await update_role_service(role_id, body, db, principal=principal)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
	role_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a role."""
	await delete_role_service(role_id, db, principal=principal)


# role members


@router.get("/{role_id}/members", response_model=list[UserSchema])
async def read_role_members(
	role_id: TypeID,
	skip: int = 0,
	limit: int = 100,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[User]:
	"""list users assigned to a role."""
	return await list_role_members(
		role_id, db, principal=principal, skip=skip, limit=limit
	)


@router.put("/{role_id}/members", response_model=list[UserSchema])
async def set_role_members(
	role_id: TypeID,
	body: list[TypeID],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[User]:
	"""replace the entire member list for a role with the given user IDs."""
	return await set_role_members_service(role_id, body, db, principal=principal)
