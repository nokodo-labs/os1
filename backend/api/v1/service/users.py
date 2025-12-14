"""Service helpers for user operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.schemas.user import UserCreate
from nokodo_ai.utils.security import hash_password


async def list_users(
	session: AsyncSession,
	skip: int = 0,
	limit: int = 100,
) -> list[User]:
	result = await session.execute(select(User).offset(skip).limit(limit))
	return list(result.scalars().all())


async def get_user(user_id: int, session: AsyncSession) -> User:
	result = await session.execute(select(User).where(User.id == user_id))
	user = result.scalar_one_or_none()

	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)

	return user


async def create_user(user_in: UserCreate, session: AsyncSession) -> User:
	result = await session.execute(select(User).where(User.email == user_in.email))
	if result.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Email already registered",
		)

	user = User(
		email=user_in.email,
		hashed_password=hash_password(user_in.password),
		display_name=user_in.display_name,
		is_active=user_in.is_active,
		is_superuser=user_in.is_superuser,
	)
	session.add(user)
	await session.commit()
	await session.refresh(user)
	return user
