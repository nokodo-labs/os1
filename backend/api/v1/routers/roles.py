"""role management routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.role import Role
from api.schemas.role import Role as RoleSchema
from api.schemas.role import RoleCreate, RoleUpdate
from api.v1.service import roles as roles_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleSchema])
async def read_roles(
	skip: int = 0,
	limit: int = 100,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Role]:
	"""list all roles."""
	return await roles_service.list_roles(
		db, principal=principal, skip=skip, limit=limit
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
