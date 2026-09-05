"""authorized user session management operations."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.user import User
from api.models.user_session import UserSession
from api.permissions import ActionPermission
from api.v1.service.authentication import Principal
from api.v1.service.authentication.cache import mark_sessions_revoked
from api.v1.service.authentication.sessions import (
	get_user_session,
	revoke_all_sessions,
	revoke_session,
)
from api.v1.service.authentication.sessions import (
	list_user_sessions as list_user_sessions_service,
)
from api.v1.service.authorization import require_self_or_permission
from api.v1.service.events import persist_and_fanout_event, request_socket_kill
from nokodo_ai.utils.typeid import TypeID


async def list_user_sessions(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	offset: int = 0,
	limit: int = 100,
) -> list[UserSession]:
	"""list active and historical login sessions for a user."""
	require_self_or_permission(user_id, principal, ActionPermission.USERS_MANAGE)
	return await list_user_sessions_service(
		session,
		user_id,
		offset=offset,
		limit=limit,
	)


async def revoke_user_sessions(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> int:
	"""revoke all active sessions for a user."""
	require_self_or_permission(user_id, principal, ActionPermission.USERS_MANAGE)
	result = await session.execute(select(User).where(User.id == user_id))
	user = result.scalar_one_or_none()
	if user is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="user not found",
		)
	revoked_ids = await revoke_all_sessions(session, user.id)
	event = Event(
		scope=EventScope.USER,
		scope_id=user.id,
		type=EventType.USER_SESSIONS_REVOKED,
		data={
			"user_id": user.id,
			"actor_id": principal.user.id,
			"sessions_revoked": len(revoked_ids),
		},
		user_id=user.id,
	)
	await persist_and_fanout_event(session, event=event)
	await mark_sessions_revoked(revoked_ids)
	await request_socket_kill(user.id)
	return len(revoked_ids)


async def revoke_user_session(
	user_id: TypeID,
	session_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> UserSession:
	"""revoke one login session for a user."""
	require_self_or_permission(user_id, principal, ActionPermission.USERS_MANAGE)
	row = await get_user_session(session, user_id, session_id)
	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="session not found",
		)
	await revoke_session(session, row)
	event = Event(
		scope=EventScope.USER,
		scope_id=user_id,
		type=EventType.USER_SESSIONS_REVOKED,
		data={
			"user_id": user_id,
			"actor_id": principal.user.id,
			"session_id": session_id,
			"sessions_revoked": 1,
		},
		user_id=user_id,
	)
	await persist_and_fanout_event(session, event=event)
	await session.refresh(row)
	return row
