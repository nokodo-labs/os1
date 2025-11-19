"""Event endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.event import Event, EventScope
from api.models.notification import Notification
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventCreate


router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventSchema, status_code=201)
async def emit_event(
	event_in: EventCreate,
	db: AsyncSession = Depends(get_db),
) -> Event:
	"""Persist and broadcast an event."""
	event = Event(**event_in.model_dump(by_alias=True))
	db.add(event)
	await db.flush()

	if event.user_id:
		db.add(Notification(user_id=event.user_id, event_id=event.id))

	await db.commit()
	await db.refresh(event)
	return event


@router.get("", response_model=list[EventSchema])
async def list_events(
	scope: EventScope | None = None,
	thread_id: str | None = None,
	task_id: str | None = None,
	user_id: int | None = None,
	since: datetime | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""Query events with flexible filters."""
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

	result = await db.execute(stmt.limit(200))
	return list(result.scalars().all())
