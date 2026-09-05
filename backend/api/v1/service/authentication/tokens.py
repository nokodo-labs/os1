"""access and refresh token lifecycle."""

from datetime import timedelta

from fastapi import HTTPException, status
from joserfc.errors import JoseError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.models.user_session import SESSION_TYPEID_PREFIX
from api.settings import settings
from api.v1.schemas.auth import Token
from api.v1.service.authentication.sessions import (
	advance_session,
	create_session,
	get_session,
	revoke_session,
)
from nokodo_ai.utils.security import create_jwt_token, decode_jwt_token
from nokodo_ai.utils.typeid import TypeID, assert_typeid


def create_access_token(user_id: str, session_id: str) -> str:
	"""create a short-lived API access token."""
	return create_jwt_token(
		subject=user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		expires_delta=timedelta(minutes=settings.security.access_token_expire_minutes),
		additional_claims={"sid": session_id},
	)


def create_refresh_token(user_id: str, session_id: str, jti: str) -> str:
	"""create a long-lived refresh token."""
	return create_jwt_token(
		subject=user_id,
		secret_key=settings.security.secret_key,
		algorithm=settings.security.jwt_algorithm,
		expires_delta=timedelta(days=settings.security.refresh_token_expire_days),
		additional_claims={"typ": "refresh", "sid": session_id, "jti": jti},
	)


def session_claims(payload: dict[str, object]) -> tuple[TypeID, str]:
	"""extract and validate refresh-token session claims."""
	session_id = payload.get("sid")
	jti = payload.get("jti")
	if not session_id or not isinstance(jti, str):
		raise ValueError("missing session claims")
	return TypeID(assert_typeid(str(session_id), prefix=SESSION_TYPEID_PREFIX)), jti


def credentials_exception(clear_cookie: bool = False) -> HTTPException:
	"""build the standard token validation failure."""
	headers = {"WWW-Authenticate": "Bearer"}
	if clear_cookie:
		headers["X-Clear-Refresh-Cookie"] = "true"
	return HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="could not validate credentials",
		headers=headers,
	)


async def create_token_pair(
	user: User,
	session: AsyncSession,
	client_key: str | None = None,
	user_agent: str | None = None,
) -> Token:
	"""create a session row and token pair for a successful login."""
	if not user.is_active:
		raise HTTPException(status_code=400, detail="inactive user")
	row = await create_session(
		session,
		user_id=user.id,
		client_key=client_key,
		user_agent=user_agent,
	)
	return Token(
		access_token=create_access_token(str(user.id), str(row.id)),
		token_type="bearer",
		refresh_token=create_refresh_token(str(user.id), str(row.id), row.current_jti),
	)


async def refresh_token_for_user(
	refresh_token: str,
	session: AsyncSession,
) -> Token:
	"""validate and rotate a refresh token into a new token pair."""
	try:
		payload = decode_jwt_token(
			refresh_token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
	except JoseError:
		raise credentials_exception()
	if payload.get("typ") != "refresh":
		raise credentials_exception()
	user_id_raw = payload.get("sub")
	if not user_id_raw:
		raise credentials_exception()
	try:
		user_id = TypeID(assert_typeid(str(user_id_raw), prefix="user"))
		session_id, jti = session_claims(payload)
	except ValueError:
		raise credentials_exception(clear_cookie=True)
	row = await get_session(session, session_id)
	if row is None or row.user_id != user_id or not row.is_active:
		raise credentials_exception(clear_cookie=True)
	user = await session.scalar(select(User).where(User.id == user_id))
	if user is None or not user.is_active:
		raise credentials_exception(clear_cookie=True)
	refresh_jti = await advance_session(session, row, jti)
	if refresh_jti is None:
		await revoke_session(session, row)
		raise credentials_exception(clear_cookie=True)
	return Token(
		access_token=create_access_token(str(user.id), str(row.id)),
		token_type="bearer",
		refresh_token=create_refresh_token(str(user.id), str(row.id), refresh_jti),
	)


async def revoke_session_from_token(
	refresh_token: str,
	session: AsyncSession,
) -> None:
	"""best-effort revoke the session behind a refresh token."""
	try:
		payload = decode_jwt_token(
			refresh_token,
			secret_key=settings.security.secret_key,
			algorithms=[settings.security.jwt_algorithm],
		)
		if payload.get("typ") != "refresh":
			return
		session_id, _ = session_claims(payload)
	except JoseError, ValueError:
		return
	row = await get_session(session, session_id)
	if row is not None:
		await revoke_session(session, row)
