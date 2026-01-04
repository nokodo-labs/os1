"""event service helpers.

this module centralizes event persistence + websocket broadcasting.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import NOTIFICATION_EVENTS
from api.models.notification import Notification
from api.schemas.event import EventCreate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.connection_manager import event_connections


async def publish_event(
	session: AsyncSession,
	*,
	event: Event,
	create_notification: bool | None = None,
) -> Event:
	"""persist an event (optionally create a notification) and broadcast it."""
	session.add(event)
	await session.flush()

	if create_notification is None:
		create_notification = event.type in NOTIFICATION_EVENTS

	if create_notification:
		if not event.user_id:
			raise ValueError("notification events require user_id")
		session.add(Notification(user_id=str(event.user_id), event_id=event.id))

	await session.commit()
	await session.refresh(event)

	await event_connections.broadcast_event(event)
	return event


async def emit_event(
	event_in: EventCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Event:
	require_permission(principal, "events:manage")
	if event_in.user_id is not None and not principal.is_admin:
		target_user_id = str(event_in.user_id)
		if target_user_id != principal.user_id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
	event = Event(**event_in.model_dump(by_alias=True))
	return await publish_event(
		session,
		event=event,
		create_notification=bool(event.user_id),
	)


async def list_events(
	session: AsyncSession,
	*,
	principal: Principal,
	scope: EventScope | None = None,
	thread_id: str | None = None,
	task_id: str | None = None,
	user_id: str | None = None,
	since: datetime | None = None,
) -> list[Event]:
	require_permission(principal, "events:manage")
	stmt = select(Event).order_by(Event.created_at.desc())

	if scope is not None:
		stmt = stmt.where(Event.scope == scope)
	if thread_id is not None:
		stmt = stmt.where(Event.thread_id == thread_id)
	if task_id is not None:
		stmt = stmt.where(Event.task_id == task_id)
	if user_id is not None:
		stmt = stmt.where(Event.user_id == user_id)
	if since is not None:
		stmt = stmt.where(Event.created_at >= since)

	result = await session.execute(stmt.limit(200))
	return list(result.scalars().all())
