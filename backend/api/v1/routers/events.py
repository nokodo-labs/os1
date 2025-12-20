"""Event routers."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.event import Event, EventScope
from api.schemas.event import Event as EventSchema
from api.schemas.event import EventCreate
from api.typeid import TypeID
from api.v1.service import events as event_service


router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventSchema, status_code=201)
async def emit_event(
	event_in: EventCreate,
	db: AsyncSession = Depends(get_db),
) -> Event:
	"""Persist and broadcast an event."""
	return await event_service.emit_event(event_in, db)


@router.get("", response_model=list[EventSchema])
async def list_events(
	scope: EventScope | None = None,
	thread_id: TypeID | None = None,
	task_id: TypeID | None = None,
	user_id: TypeID | None = None,
	since: datetime | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[Event]:
	"""Query events with flexible filters."""
	return await event_service.list_events(
		db,
		scope=scope,
		thread_id=thread_id,
		task_id=task_id,
		user_id=user_id,
		since=since,
	)
