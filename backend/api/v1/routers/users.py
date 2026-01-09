"""User routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.schemas.sorting import CommonSortBy, SortDir
from api.schemas.user import User as UserSchema
from api.schemas.user import UserCreate
from api.v1.service import users as user_service
from api.v1.service.auth import Principal, get_current_principal, get_optional_user
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
	"""Retrieve users."""
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
	"""Get user by ID."""
	return await user_service.get_user(user_id, db, principal=principal)


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	current_user: User | None = Depends(get_optional_user),
	db: AsyncSession = Depends(get_db),
) -> User:
	"""Create new user."""
	return await user_service.create_user(user_in, db, actor=current_user)
