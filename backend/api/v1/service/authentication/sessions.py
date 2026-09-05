"""server-side login session lifecycle."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user_client import UserClient
from api.models.user_session import UserSession
from api.settings import settings
from api.v1.service.authentication.cache import (
	fill_session_validity,
	get_session_validity,
	mark_session_revoked,
)
from nokodo_ai.utils.security import new_jti
from nokodo_ai.utils.typeid import TypeID


REFRESH_REUSE_GRACE = timedelta(seconds=60)
type JtiValidity = Literal["current", "grace", "invalid"]


def _refresh_lifetime() -> timedelta:
	"""lifetime granted to a session on creation and each rotation."""
	return timedelta(days=settings.security.refresh_token_expire_days)


async def _resolve_client_id(
	session: AsyncSession,
	user_id: TypeID,
	client_key: str | None,
	user_agent: str | None,
) -> TypeID | None:
	"""link an existing user client by key, spawning a minimal row if missing."""
	if not client_key:
		return None
	result = await session.execute(
		select(UserClient).where(
			UserClient.user_id == user_id,
			UserClient.client_key == client_key,
		)
	)
	client = result.scalar_one_or_none()
	if client is None:
		client = UserClient(
			user_id=user_id,
			client_key=client_key,
			user_agent=user_agent,
			last_seen_at=datetime.now(UTC),
		)
		session.add(client)
		await session.flush()
	return client.id


async def create_session(
	session: AsyncSession,
	user_id: TypeID,
	client_key: str | None = None,
	user_agent: str | None = None,
) -> UserSession:
	"""create and commit a session row for a fresh login."""
	now = datetime.now(UTC)
	client_id = await _resolve_client_id(session, user_id, client_key, user_agent)
	row = UserSession(
		user_id=user_id,
		client_id=client_id,
		current_jti=new_jti(),
		last_used_at=now,
		expires_at=now + _refresh_lifetime(),
		user_agent=user_agent,
	)
	session.add(row)
	await session.commit()
	await session.refresh(row)
	return row


async def get_session(session: AsyncSession, session_id: TypeID) -> UserSession | None:
	"""load a session row by ID."""
	return await session.scalar(select(UserSession).where(UserSession.id == session_id))


async def list_user_sessions(
	session: AsyncSession,
	user_id: TypeID,
	offset: int = 0,
	limit: int = 100,
) -> list[UserSession]:
	"""list active and historical sessions for a user."""
	return list(
		await session.scalars(
			select(UserSession)
			.where(UserSession.user_id == user_id)
			.order_by(UserSession.created_at.desc(), UserSession.id.desc())
			.offset(offset)
			.limit(limit)
		)
	)


async def get_user_session(
	session: AsyncSession,
	user_id: TypeID,
	session_id: TypeID,
) -> UserSession | None:
	"""load one session through its owning user path."""
	return await session.scalar(
		select(UserSession).where(
			UserSession.id == session_id,
			UserSession.user_id == user_id,
		)
	)


async def session_alive(session: AsyncSession, session_id: TypeID) -> bool:
	"""whether the session is live, served from cache with DB fallback."""
	cached = await get_session_validity(session_id)
	if cached is not None:
		return cached
	row = await get_session(session, session_id)
	alive = row is not None and row.is_active
	await fill_session_validity(session_id, alive)
	return alive


def check_jti(row: UserSession, jti: str, now: datetime | None = None) -> JtiValidity:
	"""classify a presented refresh jti against session rotation state."""
	now = now or datetime.now(UTC)
	if jti == row.current_jti:
		return "current"
	if (
		row.prev_jti is not None
		and jti == row.prev_jti
		and row.rotated_at is not None
		and now - row.rotated_at <= REFRESH_REUSE_GRACE
	):
		return "grace"
	return "invalid"


async def touch_session(session: AsyncSession, row: UserSession) -> None:
	"""record use without rotating and commit."""
	row.last_used_at = datetime.now(UTC)
	session.add(row)
	await session.commit()


async def advance_session(
	session: AsyncSession,
	row: UserSession,
	jti: str,
) -> str | None:
	"""advance refresh rotation state and return the jti to reissue."""
	validity = check_jti(row, jti)
	if validity == "current":
		now = datetime.now(UTC)
		result = await session.execute(
			update(UserSession)
			.where(
				UserSession.id == row.id,
				UserSession.current_jti == jti,
				UserSession.revoked_at.is_(None),
			)
			.values(
				prev_jti=jti,
				current_jti=new_jti(),
				rotated_at=now,
				last_used_at=now,
				expires_at=now + _refresh_lifetime(),
			)
			.returning(UserSession.current_jti)
		)
		rotated = result.scalar_one_or_none()
		await session.commit()
		if rotated is not None:
			return rotated
		await session.refresh(row)
		if not row.is_active:
			return None
		validity = check_jti(row, jti)
	if validity == "grace":
		await touch_session(session, row)
		return row.current_jti
	return None


async def revoke_session(session: AsyncSession, row: UserSession) -> None:
	"""revoke one session, commit, and write through to cache."""
	if row.revoked_at is None:
		row.revoked_at = datetime.now(UTC)
		session.add(row)
	await session.commit()
	await mark_session_revoked(row.id)


async def revoke_all_sessions(session: AsyncSession, user_id: TypeID) -> list[TypeID]:
	"""stage revocation of every live session for one user."""
	now = datetime.now(UTC)
	result = await session.execute(
		update(UserSession)
		.where(
			UserSession.user_id == user_id,
			UserSession.revoked_at.is_(None),
			UserSession.expires_at > now,
		)
		.values(revoked_at=now)
		.returning(UserSession.id)
	)
	return [TypeID(session_id) for session_id in result.scalars().all()]


async def purge_expired_sessions(
	session: AsyncSession,
	cutoff: datetime,
	limit: int,
) -> int:
	"""hard-delete and commit one bounded batch of expired sessions."""
	candidates = (
		select(UserSession.id)
		.where(UserSession.expires_at < cutoff)
		.order_by(UserSession.expires_at, UserSession.id)
		.limit(limit)
		.cte("expired_user_sessions")
	)
	result = await session.execute(
		delete(UserSession)
		.where(UserSession.id.in_(select(candidates.c.id)))
		.returning(UserSession.id)
	)
	deleted = len(result.scalars().all())
	await session.commit()
	return deleted
