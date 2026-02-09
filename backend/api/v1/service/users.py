"""service helpers for user operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.many_to_many import user_role_association
from api.models.user import User
from api.permissions import ActionPermission
from api.schemas.user import UserCreate, UserUpdate
from api.settings import settings
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
			detail="user not found",
		)

	return user


async def create_user(
	user_in: UserCreate,
	session: AsyncSession,
	*,
	principal: Principal | None = None,
) -> User:
	user_count = await session.scalar(select(func.count()).select_from(User))
	is_bootstrap = (user_count or 0) == 0
	actor = principal.user if principal else None

	# determine what privilege level the new user can have:
	# - bootstrap (first user): must request superuser explicitly (console setup)
	# - unauthenticated: regular user only (is_active=True, is_superuser=False)
	# - authenticated superuser: can set any privileges
	if is_bootstrap:
		if user_in.is_superuser is not True:
			console_origin_value = settings.branding.public_console_origin
			console_origin = (
				str(console_origin_value) if console_origin_value is not None else None
			)
			detail: dict[str, str | None] = {
				"code": "bootstrap_required",
				"message": "this instance needs an admin created in the console first",
				"console_origin": console_origin,
			}
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail=detail,
			)

		# first user requested to be superuser
		is_active = True
		is_superuser = True
	elif actor is not None:
		if not actor.is_active:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="inactive user",
			)

		if principal is None:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

		if not principal.is_admin and not principal.has_permission(
			str(ActionPermission.USERS_MANAGE)
		):
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)

		# allow signups toggle does not block admin/authorized creation
		if principal.is_admin:
			is_active = user_in.is_active if user_in.is_active is not None else True
			is_superuser = (
				user_in.is_superuser if user_in.is_superuser is not None else False
			)
		else:
			is_active = True
			is_superuser = False
	else:
		if not settings.security.allow_signups:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="signups are disabled",
			)
		# unauthenticated: regular user only
		is_active = True
		is_superuser = False

	result = await session.execute(select(User).where(User.email == user_in.email))
	if result.scalar_one_or_none():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="email already registered",
		)

	user = User(
		email=user_in.email,
		hashed_password=hash_password(user_in.password),
		display_name=user_in.display_name,
		is_active=is_active,
		is_superuser=is_superuser,
	)
	session.add(user)
	await session.flush()

	if actor is None:
		role_ids = settings.security.auto_signup_role_ids
		if role_ids:
			await session.execute(
				insert(user_role_association),
				[{"user_id": str(user.id), "role_id": str(rid)} for rid in role_ids],
			)

	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		msg = str(exc.orig).lower()
		if "email" in msg and "unique" in msg:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="email already registered",
			) from None
		elif "foreign key" in msg and "user_roles" in msg:
			raise HTTPException(
				status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
				detail="invalid role reference in auto_signup_role_ids",
			) from None
		else:
			raise exc
	await session.refresh(user)
	return user


async def update_user(
	user_id: str,
	user_in: UserUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> User:
	if not principal.is_admin and str(user_id) != str(principal.user.id):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

	if not principal.is_admin:
		if (
			user_in.email is not None
			or user_in.password is not None
			or user_in.is_active is not None
			or user_in.display_name is not None
			or user_in.avatar_url is not None
			or user_in.integration_tokens is not None
			or user_in.usage_quotas is not None
			or user_in.role_ids is not None
		):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="unsupported fields",
			)
		if user_in.preferences is None:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="preferences is required",
			)

	user = await get_user(user_id, session, principal=principal)

	if user_in.preferences is not None:
		user.preferences = user_in.preferences.model_dump(
			mode="json",
			by_alias=True,
			exclude_none=True,
		)

	if principal.is_admin:
		if user_in.email is not None:
			user.email = user_in.email
		if user_in.display_name is not None:
			user.display_name = user_in.display_name
		if user_in.avatar_url is not None:
			user.avatar_url = user_in.avatar_url
		if user_in.is_active is not None:
			user.is_active = user_in.is_active
		if user_in.integration_tokens is not None:
			user.integration_tokens = dict(user_in.integration_tokens)
		if user_in.usage_quotas is not None:
			user.usage_quotas = dict(user_in.usage_quotas)
		if user_in.password is not None:
			user.hashed_password = hash_password(user_in.password)
		if user_in.role_ids is not None:
			# clear existing roles and insert new ones via the secondary table.
			# FK constraints on user_roles will reject non-existent role IDs.
			await session.execute(
				delete(user_role_association).where(
					user_role_association.c.user_id == str(user.id)
				)
			)
			if user_in.role_ids:
				await session.execute(
					insert(user_role_association),
					[
						{"user_id": str(user.id), "role_id": str(rid)}
						for rid in user_in.role_ids
					],
				)

	session.add(user)
	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail=f"invalid reference: {exc.orig}",
		) from None
	await session.refresh(user)
	return user
