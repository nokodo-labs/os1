"""role management routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.role import Role
from api.models.user import User
from api.schemas.role import Role as RoleSchema
from api.schemas.role import RoleCreate, RoleSortBy, RoleUpdate
from api.schemas.sorting import SortDir
from api.schemas.user import User as UserSchema
from api.v1.service import roles as roles_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleSchema])
async def read_roles(
	skip: int = 0,
	limit: int = 100,
	sort_by: RoleSortBy = "priority",
	sort_dir: SortDir = "desc",
	user_id: TypeID | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Role]:
	"""list all roles. optionally filter by user_id."""
	return await roles_service.list_roles(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		user_id=user_id,
	)


@router.get("/{role_id}", response_model=RoleSchema)
async def read_role(
	role_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""get a role by id."""
	return await roles_service.get_role(role_id, db, principal=principal)


@router.post("", response_model=RoleSchema, status_code=status.HTTP_201_CREATED)
async def create_role(
	role_in: RoleCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""create a new role."""
	return await roles_service.create_role(role_in, db, principal=principal)


@router.patch("/{role_id}", response_model=RoleSchema)
async def update_role(
	role_id: TypeID,
	body: RoleUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Role:
	"""update an existing role."""
	return await roles_service.update_role(role_id, body, db, principal=principal)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
	role_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a role."""
	await roles_service.delete_role(role_id, db, principal=principal)


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
	return await roles_service.list_role_members(
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
	return await roles_service.set_role_members(role_id, body, db, principal=principal)
