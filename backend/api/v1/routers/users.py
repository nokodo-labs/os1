"""User routers."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.schemas.user import User as UserSchema
from api.schemas.user import UserCreate
from api.v1.service import users as user_service


router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserSchema])
async def read_users(
	skip: int = 0,
	limit: int = 100,
	db: AsyncSession = Depends(get_db),
) -> list[User]:
	"""Retrieve users."""
	return await user_service.list_users(db, skip=skip, limit=limit)


@router.get("/{user_id}", response_model=UserSchema)
async def read_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
) -> User:
	"""Get user by ID (future permissions will restrict visibility)."""
	return await user_service.get_user(user_id, db)


@router.post("", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	db: AsyncSession = Depends(get_db),
) -> User:
	"""Create new user."""
	return await user_service.create_user(user_in, db)
