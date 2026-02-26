from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.settings import settings
from api.v1.schemas.auth import PasswordChange, Token
from api.v1.service import auth as auth_service


router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = "/"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
	"""set refresh token as HttpOnly cookie."""
	max_age = int(
		timedelta(days=settings.security.refresh_token_expire_days).total_seconds()
	)
	samesite = "none" if settings.security.auth_cookie_secure else "strict"
	response.set_cookie(
		key=auth_service.REFRESH_COOKIE_NAME,
		value=refresh_token,
		httponly=True,
		secure=settings.security.auth_cookie_secure,
		samesite=samesite,
		path=REFRESH_COOKIE_PATH,
		max_age=max_age,
	)


def _clear_refresh_cookie(response: Response) -> None:
	"""clear refresh token cookie."""
	samesite = "none" if settings.security.auth_cookie_secure else "strict"
	response.delete_cookie(
		key=auth_service.REFRESH_COOKIE_NAME,
		path=REFRESH_COOKIE_PATH,
		samesite=samesite,
		secure=settings.security.auth_cookie_secure,
	)


@router.post("/login/access-token", response_model=Token)
async def login_access_token(
	response: Response,
	form_data: OAuth2PasswordRequestForm = Depends(),
	session: AsyncSession = Depends(get_db),
) -> Token:
	"""OAuth2 compatible token login, get an access token for future requests."""
	if settings.security.oidc.only:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="oidc login required",
		)
	user = await auth_service.authenticate_user(
		session=session, identifier=form_data.username, password=form_data.password
	)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="incorrect email, username, or password",
		)

	token_pair = await auth_service.create_token_pair(user)
	if token_pair.refresh_token:
		_set_refresh_cookie(response, token_pair.refresh_token)

	# Don't send refresh_token in response body (it's HttpOnly)
	return Token(access_token=token_pair.access_token, token_type=token_pair.token_type)


@router.post(
	"/refresh",
	response_model=Token,
	dependencies=[Depends(auth_service.require_csrf_origin)],
)
async def refresh_access_token(
	response: Response,
	session: AsyncSession = Depends(get_db),
	refresh_token: str | None = Cookie(
		default=None, alias=auth_service.REFRESH_COOKIE_NAME
	),
) -> Token:
	"""exchange refresh token for new access token (sliding refresh)."""
	if not refresh_token:
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="could not validate credentials",
			headers={"WWW-Authenticate": "Bearer"},
		)

	try:
		token_pair = await auth_service.refresh_token_for_user(refresh_token, session)
	except HTTPException as e:
		if e.headers and e.headers.get("X-Clear-Refresh-Cookie") == "true":
			_clear_refresh_cookie(response)
		raise

	if token_pair.refresh_token:
		_set_refresh_cookie(response, token_pair.refresh_token)

	return Token(access_token=token_pair.access_token, token_type=token_pair.token_type)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
	body: PasswordChange,
	principal: auth_service.Principal = Depends(auth_service.get_current_principal),
	session: AsyncSession = Depends(get_db),
) -> None:
	"""change the authenticated user's password."""
	if settings.security.oidc.only:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="password change not available with oidc-only authentication",
		)
	await auth_service.change_password(
		session,
		principal,
		current_password=body.current_password,
		new_password=body.new_password,
	)


@router.post(
	"/logout",
	status_code=status.HTTP_204_NO_CONTENT,
	dependencies=[Depends(auth_service.require_csrf_origin)],
)
async def logout(response: Response) -> None:
	"""clear refresh token cookie to log out."""
	_clear_refresh_cookie(response)
