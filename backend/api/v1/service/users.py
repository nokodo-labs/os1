"""Service helpers for user operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.schemas.user import UserCreate
from api.v1.service.auth import Principal
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.security import hash_password


async def list_users(
	session: AsyncSession,
	*,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
) -> list[User]:
	if not principal.is_admin:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
	stmt = apply_sort(
		select(User),
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": User.created_at,
			"updated_at": User.updated_at,
			"email": User.email,
			"display_name": User.display_name,
			"is_active": User.is_active,
			"is_superuser": User.is_superuser,
		},
		tie_breaker=User.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def get_user(
	user_id: str,
	session: AsyncSession,
	*,
	principal: Principal,
) -> User:
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	result = await session.execute(select(User).where(User.id == user_id))
	user = result.scalar_one_or_none()

	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)

	return user


async def create_user(
	user_in: UserCreate,
	session: AsyncSession,
	*,
	actor: User | None = None,
) -> User:
	user_count = await session.scalar(select(func.count()).select_from(User))
	is_bootstrap = (user_count or 0) == 0

	if not is_bootstrap:
		if actor is None:
			raise HTTPException(
				status_code=status.HTTP_401_UNAUTHORIZED,
				detail="not authenticated",
			)
		if not actor.is_active:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="inactive user",
			)
		if not actor.is_superuser:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

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
		is_active=True if is_bootstrap else user_in.is_active,
		is_superuser=True if is_bootstrap else user_in.is_superuser,
	)
	session.add(user)
	await session.commit()
	await session.refresh(user)
	return user
