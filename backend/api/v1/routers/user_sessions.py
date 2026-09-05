"""user session routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.user_session import UserSession
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.users import list_user_sessions
from api.v1.service.users import (
	revoke_user_session as service_revoke_user_session,
)
from api.v1.service.users import (
	revoke_user_sessions as service_revoke_user_sessions,
)
from api.v1.tasks.user_sessions import run_user_session_purge
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(tags=["user sessions"])


@router.post("/sessions/purge/run")
async def run_session_purge(
	batch_size: Annotated[int | None, Query(ge=1, le=10000)] = None,
	principal: Principal = Depends(get_current_principal),
) -> JSONObject:
	"""manually purge one batch of expired user sessions."""
	require_admin(principal)
	return await run_user_session_purge(
		batch_size=batch_size,
		respect_enabled=False,
	)


@router.get("/{user_id}/sessions", response_model=list[UserSession])
async def read_user_sessions(
	user_id: TypeID,
	offset: Annotated[int, Query(ge=0)] = 0,
	limit: Annotated[int, Query(ge=1, le=500)] = 100,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[UserSession]:
	"""list active and historical login sessions for a user."""
	rows = await list_user_sessions(
		user_id,
		db,
		principal,
		offset=offset,
		limit=limit,
	)
	return [UserSession.model_validate(row) for row in rows]


@router.post("/{user_id}/sessions/revoke", response_model=int)
async def revoke_user_sessions(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""revoke all active sessions for a user."""
	return await service_revoke_user_sessions(
		user_id,
		db,
		principal,
	)


@router.post("/{user_id}/sessions/{session_id}/revoke", response_model=UserSession)
async def revoke_user_session(
	user_id: TypeID,
	session_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> UserSession:
	"""revoke one login session while retaining its history."""
	row = await service_revoke_user_session(
		user_id,
		session_id,
		db,
		principal,
	)
	return UserSession.model_validate(row)
