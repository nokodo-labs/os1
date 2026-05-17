"""service helpers for user clients."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.user_client import UserClient
from api.schemas.user_client import (
	UserClientPatch,
	UserClientPreferences,
	UserClientUpsert,
)
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


def _preferences_data(payload: UserClientPreferences) -> JSONObject:
	"""serialize client preference overrides for storage."""
	data: JSONObject = payload.model_dump(mode="json", by_alias=True)
	return {key: value for key, value in data.items() if value != {}}


def _ensure_user_access(user_id: TypeID, principal: Principal) -> None:
	"""ensure the principal can manage clients for the user path."""
	if not principal.is_admin and user_id != principal.user_id:
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


async def _get_client(
	user_id: TypeID,
	client_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> UserClient:
	"""return one client visible through the user path."""
	_ensure_user_access(user_id, principal)
	stmt = select(UserClient).where(
		UserClient.id == client_id,
		UserClient.user_id == user_id,
	)
	result = await session.execute(stmt)
	client = result.scalars().one_or_none()
	if client is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="client not found",
		)
	return client


async def upsert_user_client(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	payload: UserClientUpsert,
) -> UserClient:
	"""create or refresh a stable client record for a user."""
	_ensure_user_access(user_id, principal)
	stmt = select(UserClient).where(
		UserClient.user_id == user_id,
		UserClient.client_key == payload.client_key,
	)
	result = await session.execute(stmt)
	client = result.scalars().one_or_none()
	now = datetime.now(tz=UTC)

	if client is None:
		client = UserClient(
			user_id=user_id,
			client_key=payload.client_key,
			name=payload.name,
			user_agent=payload.user_agent,
			info=payload.info,
			last_seen_at=now,
		)
		session.add(client)
	else:
		client.name = payload.name
		client.user_agent = payload.user_agent
		client.info = payload.info
		client.last_seen_at = now

	await session.commit()
	await session.refresh(client)
	return client


async def list_user_clients(
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> list[UserClient]:
	"""list clients registered by a user."""
	_ensure_user_access(user_id, principal)
	stmt = (
		select(UserClient)
		.where(UserClient.user_id == user_id)
		.order_by(
			UserClient.last_seen_at.desc().nullslast(), UserClient.created_at.desc()
		)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def update_user_client(
	user_id: TypeID,
	client_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	payload: UserClientPatch,
) -> UserClient:
	"""update client-specific label or info."""
	client = await _get_client(user_id, client_id, session, principal)
	updates = payload.model_dump(exclude_unset=True)
	if "name" in updates:
		client.name = payload.name
	if "info" in updates and payload.info is not None:
		client.info = payload.info
	await session.commit()
	await session.refresh(client)
	return client


async def update_user_client_preferences(
	user_id: TypeID,
	client_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	payload: UserClientPreferences,
	origin_session_id: str | None = None,
) -> UserClient:
	"""replace client-specific preference overrides."""
	client = await _get_client(user_id, client_id, session, principal)
	client.preferences = _preferences_data(payload)
	await session.commit()
	await session.refresh(client)

	event = Event(
		scope=EventScope.USER,
		scope_id=user_id,
		type=EventType.USER_CLIENT_PREFERENCES_UPDATED,
		data={
			"user_id": str(user_id),
			"client_id": str(client.id),
			"preferences": client.preferences,
		},
		user_id=user_id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return client


async def delete_user_client(
	user_id: TypeID,
	client_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete one user client and attached push subscriptions."""
	client = await _get_client(user_id, client_id, session, principal)
	await session.delete(client)
	await session.commit()
