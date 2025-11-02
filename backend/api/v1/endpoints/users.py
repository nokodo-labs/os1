"""User endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.user import User
from api.schemas.user import User as UserSchema
from api.schemas.user import UserCreate


router = APIRouter()


@router.get("/", response_model=list[UserSchema])
async def read_users(
	skip: int = 0,
	limit: int = 100,
	db: AsyncSession = Depends(get_db),
) -> list[User]:
	"""Retrieve users."""
	result = await db.execute(select(User).offset(skip).limit(limit))
	return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserSchema)
async def read_user(
	user_id: int,
	db: AsyncSession = Depends(get_db),
) -> User:
	"""Get user by ID."""
	result = await db.execute(select(User).where(User.id == user_id))
	user = result.scalar_one_or_none()

	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)

	return user


@router.post("/", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
	user_in: UserCreate,
	db: AsyncSession = Depends(get_db),
) -> User:
	"""Create new user."""
	# TODO: Hash password before storing
	user = User(
		email=user_in.email,
		username=user_in.username,
		hashed_password=user_in.password,  # TODO: Hash this
		is_active=user_in.is_active,
		is_superuser=user_in.is_superuser,
	)

	db.add(user)
	await db.commit()
	await db.refresh(user)

	return user
