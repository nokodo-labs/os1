from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from urllib.parse import urlparse

from authlib.jose import JoseError
from fastapi import Depends, Header, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.constants import API_V1_MOUNT_PATH
from api.core.database import AsyncSessionLocal, get_db
from api.models.group import GroupMembership
from api.models.user import User
from api.settings import settings
from api.v1.schemas.token import Token, TokenPayload
from nokodo_ai.utils.security import (
	create_jwt_token,
	decode_jwt_token,
	verify_password,
)
from nokodo_ai.utils.typeid import TypeID, assert_typeid


REFRESH_COOKIE_NAME = "refresh_token"


def origin_allowed(
	origin: str | None, patterns: list[str] = settings.security.allowed_hosts
) -> bool:
	if origin is None or origin == "" or origin == "null":
		return False

	hostname = urlparse(origin).hostname or ""

	for p in patterns:
		if p == "*":
			return True
		if p.startswith("."):
			# .local matches "local" and "*.local"
			domain = p[1:]
			if hostname == domain or hostname.endswith(p):
				return True
		elif hostname == p:
			return True

	return False


def require_csrf_origin(origin: str | None = Header(default=None)) -> None:
	"""CSRF guard for cookie-authenticated HTTP endpoints."""
	if not origin_allowed(origin):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="origin not allowed",
		)


def is_websocket_origin_allowed(websocket: WebSocket) -> bool:
	"""Return True if WebSocket Origin header passes CSRF validation."""
	origin = websocket.headers.get("origin")
	return origin_allowed(origin)


async def authenticate_websocket_refresh_cookie(websocket: WebSocket) -> User | None:
	"""Authenticate a WebSocket connection using refresh token cookie."""
	refresh_token = websocket.cookies.get(REFRESH_COOKIE_NAME)
	if not refresh_token:
		return None

	try:
		payload = decode_jwt_token(
			refresh_token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
		if payload.get("typ") != "refresh":
			return None
		user_id_str = payload.get("sub")
		if not user_id_str:
			return None
		user_id = TypeID(assert_typeid(str(user_id_str), prefix="user"))
	except (JoseError, ValueError):
		return None

	async with AsyncSessionLocal() as session:
		result = await session.execute(
			select(User).options(selectinload(User.role)).where(User.id == user_id)
		)
		user = result.scalar_one_or_none()

	if user and not user.is_active:
		return None

	return user


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
		detail="could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	try:
		payload = decode_jwt_token(
			token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
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


def create_access_token(user_id: str) -> str:
	"""Create a short-lived access token for API requests."""
	expires_delta = timedelta(minutes=settings.security.access_token_expire_minutes)
	return create_jwt_token(
		subject=user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		expires_delta=expires_delta,
	)


def create_refresh_token(user_id: str) -> str:
	"""Create a long-lived refresh token for silent re-authentication."""
	expires_delta = timedelta(days=settings.security.refresh_token_expire_days)
	return create_jwt_token(
		subject=user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		expires_delta=expires_delta,
		additional_claims={"typ": "refresh"},
	)


async def create_token_pair(user: User) -> Token:
	"""Create access + refresh token pair for successful login."""
	if not user.is_active:
		raise HTTPException(status_code=400, detail="Inactive user")
	access_token = create_access_token(str(user.id))
	refresh_token = create_refresh_token(str(user.id))
	return Token(
		access_token=access_token, token_type="bearer", refresh_token=refresh_token
	)


async def refresh_token_for_user(refresh_token: str, session: AsyncSession) -> Token:
	"""
	Validate refresh token and return new access+refresh tokens.
	Returns: (Token, should_clear_cookie) tuple.
	"""
	try:
		payload = decode_jwt_token(
			refresh_token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
	except JoseError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	if payload.get("typ") != "refresh":
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	user_id_str = payload.get("sub")
	if not user_id_str:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	try:
		user_id = TypeID(assert_typeid(str(user_id_str), prefix="user"))
	except ValueError:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	user_result = await session.execute(select(User).where(User.id == user_id))
	user = user_result.scalar_one_or_none()
	if not user or not user.is_active:
		# Signal router to clear cookie
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer", "X-Clear-Refresh-Cookie": "true"},
		)

	# Sliding refresh: new tokens extend session
	access_token = create_access_token(str(user.id))
	new_refresh_token = create_refresh_token(str(user.id))
	return Token(
		access_token=access_token,
		token_type="bearer",
		refresh_token=new_refresh_token,
	)
