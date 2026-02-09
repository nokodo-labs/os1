"""user routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.user import User as UserSchema
from api.schemas.user import UserCreate, UserPermissions, UserUpdate
from api.v1.service import users as user_service
from api.v1.service.auth import (
	Principal,
	get_current_principal,
	get_optional_principal,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/users", tags=["users"])


UserSortBy = Literal[
	"email",
	"display_name",
	"is_active",
	"is_superuser",
]


@router.get("", response_model=list[UserSchema])
async def read_users(
	skip: int = 0,
	limit: int = 100,
	sort_by: CommonSortBy | UserSortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[User]:
	"""retrieve users."""
	return await user_service.list_users(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/{user_id}", response_model=UserSchema)
async def read_user(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""get user by ID."""
	return await user_service.get_user(user_id, db, principal=principal)


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	principal: Principal | None = Depends(get_optional_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""create new user."""
	return await user_service.create_user(user_in, db, principal=principal)


@router.get("/{user_id}/permissions", response_model=UserPermissions)
async def read_user_permissions(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserPermissions:
	"""get resolved permissions for user."""
	if not principal.is_admin and str(user_id) != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	user = await user_service.get_user(user_id, db, principal=principal)
	as_principal = await get_current_principal(user=user, session=db)

	return UserPermissions(
		permissions=sorted(as_principal.permissions),
	)


@router.patch("/{user_id}", response_model=UserSchema)
async def update_user(
	user_id: TypeID,
	body: UserUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""update user."""
	return await user_service.update_user(user_id, body, db, principal=principal)
