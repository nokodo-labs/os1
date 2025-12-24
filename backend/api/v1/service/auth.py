from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from authlib.jose import JoseError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.constants import API_V1_MOUNT_PATH
from api.core.config import settings
from api.core.database import get_db
from api.models.group import GroupMembership
from api.models.user import User
from api.v1.schemas.token import TokenPayload
from nokodo_ai.utils.security import decode_jwt_token, verify_password


oauth2_scheme = OAuth2PasswordBearer(
	tokenUrl=f"{API_V1_MOUNT_PATH}/auth/login/access-token"
)

oauth2_scheme_optional = OAuth2PasswordBearer(
	tokenUrl=f"{API_V1_MOUNT_PATH}/auth/login/access-token",
	auto_error=False,
)


@dataclass(frozen=True, slots=True)
class Principal:
	"""Authenticated principal for authorization decisions."""

	user: User
	group_ids: tuple[str, ...]
	permissions: frozenset[str]

	@property
	def user_id(self) -> str:
		return str(self.user.id)

	@property
	def is_admin(self) -> bool:
		return bool(self.user.is_superuser)

	def has_permission(self, permission: str) -> bool:
		if self.is_admin:
			return True
		if "*" in self.permissions:
			return True
		if permission in self.permissions:
			return True
		for granted in self.permissions:
			if granted.endswith(":*") and permission.startswith(granted[:-1]):
				return True
		return False


async def authenticate_user(
	session: AsyncSession, email: str, password: str
) -> User | None:
	result = await session.execute(select(User).where(User.email == email))
	user = result.scalar_one_or_none()
	if not user:
		return None
	if not verify_password(password, user.hashed_password):
		return None
	return user


async def _user_from_token(token: str, session: AsyncSession) -> User:
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		payload = decode_jwt_token(
			token,
			secret_key=settings.SECRET_KEY,
			algorithms=[settings.ALGORITHM],
		)
		user_id = payload.get("sub")
		if user_id is None:
			raise credentials_exception
		token_data = TokenPayload(sub=user_id)
	except JoseError:
		raise credentials_exception

	result = await session.execute(
		select(User).options(selectinload(User.role)).where(User.id == token_data.sub)
	)
	user = result.scalar_one_or_none()

	if user is None:
		raise credentials_exception
	return user


async def get_current_user(
	token: Annotated[str, Depends(oauth2_scheme)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
	return await _user_from_token(token, session)


async def get_optional_user(
	token: Annotated[str | None, Depends(oauth2_scheme_optional)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
	if token is None:
		return None
	return await _user_from_token(token, session)


async def get_current_active_user(
	user: Annotated[User, Depends(get_current_user)],
) -> User:
	if not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="inactive user",
		)
	return user


async def get_current_principal(
	user: Annotated[User, Depends(get_current_active_user)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> Principal:
	group_ids_result = await session.execute(
		select(GroupMembership.group_id).where(GroupMembership.user_id == user.id)
	)
	group_ids = tuple(str(row[0]) for row in group_ids_result.all())

	permissions: list[str] = []
	if user.role is not None:
		permissions = [str(permission) for permission in user.role.permissions]

	return Principal(
		user=user,
		group_ids=group_ids,
		permissions=frozenset(permissions),
	)


async def require_admin(
	principal: Annotated[Principal, Depends(get_current_principal)],
) -> None:
	if not principal.is_admin:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
