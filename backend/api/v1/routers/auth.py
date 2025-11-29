from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.core.database import get_db
from api.models.user import User as UserModel
from api.schemas.user import User as UserSchema
from api.v1.schemas.token import Token
from api.v1.service.auth import authenticate_user, get_current_active_user
from nokodo_ai.utils.security import create_jwt_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login/access-token", response_model=Token)
async def login_access_token(
	form_data: OAuth2PasswordRequestForm = Depends(),
	session: AsyncSession = Depends(get_db),
) -> Token:
	"""OAuth2 compatible token login, get an access token for future requests."""
	user = await authenticate_user(
		session=session, email=form_data.username, password=form_data.password
	)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="Incorrect email or password",
		)
	if not user.is_active:
		raise HTTPException(status_code=400, detail="Inactive user")
	access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
	access_token = create_jwt_token(
		subject=user.id,
		secret_key=settings.SECRET_KEY,
		algorithm=settings.ALGORITHM,
		expires_delta=access_token_expires,
	)
	return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserSchema)
async def read_users_me(
	current_user: UserModel = Depends(get_current_active_user),
) -> UserModel:
	"""Get current user."""
	return current_user
