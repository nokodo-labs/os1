"""browser origin and WebSocket cookie authentication."""

from urllib.parse import urlparse

from fastapi import Header, HTTPException, WebSocket, status
from joserfc.errors import JoseError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from api.database import async_session_local
from api.models.user import User
from api.settings import settings
from api.v1.service.authentication.sessions import (
	check_jti,
	get_session,
)
from api.v1.service.authentication.tokens import session_claims
from nokodo_ai.utils.security import decode_jwt_token
from nokodo_ai.utils.typeid import TypeID, assert_typeid


REFRESH_COOKIE_NAME = "nokodo:refresh_token"


def origin_allowed(
	origin: str | None,
	patterns: list[str] = settings.security.allowed_hosts,
) -> bool:
	"""whether an Origin hostname matches the configured patterns."""
	if origin is None or origin == "" or origin == "null":
		return False
	hostname = urlparse(origin).hostname or ""
	for pattern in patterns:
		if pattern == "*":
			return True
		if pattern.startswith("."):
			domain = pattern[1:]
			if hostname == domain or hostname.endswith(pattern):
				return True
		elif hostname == pattern:
			return True
	return False


def require_csrf_origin(origin: str | None = Header(default=None)) -> None:
	"""reject cookie-authenticated HTTP requests from unknown origins."""
	if not origin_allowed(origin):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="origin not allowed",
		)


def is_websocket_origin_allowed(websocket: WebSocket) -> bool:
	"""whether the WebSocket Origin header passes CSRF validation."""
	return origin_allowed(websocket.headers.get("origin"))


async def authenticate_websocket_refresh_cookie(websocket: WebSocket) -> User | None:
	"""authenticate a WebSocket through its refresh-token cookie."""
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
		user_id_raw = payload.get("sub")
		if not user_id_raw:
			return None
		user_id = TypeID(assert_typeid(str(user_id_raw), prefix="user"))
		session_id, jti = session_claims(payload)
	except JoseError, ValueError:
		return None
	async with async_session_local() as session:
		row = await get_session(session, session_id)
		if (
			row is None
			or row.user_id != user_id
			or not row.is_active
			or check_jti(row, jti) == "invalid"
		):
			return None
		user = await session.scalar(
			select(User).options(selectinload(User.roles)).where(User.id == user_id)
		)
	if user is not None and not user.is_active:
		return None
	return user
