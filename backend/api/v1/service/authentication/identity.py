"""user identity authentication and FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from joserfc.errors import JoseError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.constants import API_V1_MOUNT_PATH
from api.database import get_db
from api.models.user import User
from api.settings import settings
from api.v1.schemas.auth import TokenPayload
from nokodo_ai.utils.security import decode_jwt_token, verify_password


oauth2_scheme = OAuth2PasswordBearer(
	tokenUrl=f"{API_V1_MOUNT_PATH}/auth/login/access-token"
)
oauth2_scheme_optional = OAuth2PasswordBearer(
	tokenUrl=f"{API_V1_MOUNT_PATH}/auth/login/access-token",
	auto_error=False,
)


async def authenticate_user(
	session: AsyncSession,
	identifier: str,
	password: str,
) -> User | None:
	"""authenticate by email or username."""
	user = await session.scalar(
		select(User).where(or_(User.email == identifier, User.username == identifier))
	)
	if user is None or not verify_password(password, user.hashed_password):
		return None
	return user


async def user_from_token(token: str, session: AsyncSession) -> User:
	"""resolve a signed access token to its user row."""
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
	user = await session.scalar(
		select(User).options(selectinload(User.roles)).where(User.id == token_data.sub)
	)
	if user is None:
		raise credentials_exception
	return user


async def get_current_user(
	token: Annotated[str, Depends(oauth2_scheme)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
	"""request dependency for a session-bound authenticated user."""
	return await user_from_token(token, session)


async def get_optional_user(
	token: Annotated[str | None, Depends(oauth2_scheme_optional)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
	"""request dependency for a user when a token is present."""
	if token is None:
		return None
	return await user_from_token(token, session)


async def get_current_active_user(
	user: Annotated[User, Depends(get_current_user)],
) -> User:
	"""request dependency that rejects inactive authenticated users."""
	if not user.is_active:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="inactive user",
		)
	return user
