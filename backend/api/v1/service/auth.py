from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.constants import API_V1_MOUNT_PATH
from api.core.config import settings
from api.core.database import get_db
from api.models.user import User
from api.v1.schemas.token import TokenPayload
from nokodo_ai.utils.security import decode_jwt_token, verify_password


oauth2_scheme = OAuth2PasswordBearer(
	tokenUrl=f"{API_V1_MOUNT_PATH}/auth/login/access-token"
)


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


async def get_current_user(
	token: Annotated[str, Depends(oauth2_scheme)],
	session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
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
		token_data = TokenPayload(sub=int(user_id))
	except JWTError:
		raise credentials_exception

	result = await session.execute(select(User).where(User.id == token_data.sub))
	user = result.scalar_one_or_none()

	if user is None:
		raise credentials_exception
	return user


async def get_current_active_user(
	current_user: Annotated[User, Depends(get_current_user)],
) -> User:
	if not current_user.is_active:
		raise HTTPException(status_code=400, detail="Inactive user")
	return current_user
