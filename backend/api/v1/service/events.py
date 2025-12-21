"""Service layer for event operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.notification import Notification
from api.schemas.event import EventCreate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission


async def emit_event(
	event_in: EventCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Event:
	require_permission(principal, "events:manage")
	event = Event(**event_in.model_dump(by_alias=True))
	session.add(event)
	await session.flush()

	if event.user_id:
		session.add(Notification(user_id=event.user_id, event_id=event.id))

	await session.commit()
	await session.refresh(event)
	return event


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
