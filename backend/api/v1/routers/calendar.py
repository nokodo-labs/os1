"""calendar routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.calendar import Calendar, CalendarEvent
from api.permissions import ResourceType
from api.schemas.access_rule import AccessRuleCreate, AccessRuleResponse
from api.schemas.calendar import (
	Calendar as CalendarSchema,
)
from api.schemas.calendar import (
	CalendarCreate,
	CalendarEventCreate,
	CalendarEventListFilters,
	CalendarEventSortBy,
	CalendarEventUpdate,
	CalendarSortBy,
	CalendarUpdate,
)
from api.schemas.calendar import (
	CalendarEvent as CalendarEventSchema,
)
from api.schemas.scheduled_item import (
	CalendarOccurrenceCancel,
	CalendarOccurrenceEdit,
	CalendarSeriesEdit,
	ScheduledItem,
)
from api.schemas.search import CursorPage, SearchMode, SearchParams, SearchResultItem
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import calendar as calendar_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/calendars", tags=["calendars"])


@router.get("", response_model=list[CalendarSchema])
async def list_calendars(
	skip: int = 0,
	limit: int = Query(default=100, ge=1, le=500),
	sort_by: CalendarSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Calendar]:
	"""list calendars accessible to the current user."""
	return await calendar_service.list_calendars(
		db,
		principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.post(
	"",
	response_model=CalendarSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_calendar(
	data: CalendarCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Calendar:
	"""create a calendar."""
	return await calendar_service.create_calendar(
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/search", response_model=CursorPage[SearchResultItem])
async def search_calendars(
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	cursor: str | None = Query(default=None),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CursorPage[SearchResultItem]:
	"""search calendar events with cursor-based pagination."""
	return await calendar_service.search_calendar_events(
		q,
		db,
		principal=principal,
		limit=limit,
		cursor=cursor,
		search_params=SearchParams(mode=mode),
	)


@router.get("/{calendar_id}", response_model=CalendarSchema)
async def get_calendar(
	calendar_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Calendar:
	"""get a calendar."""
	return await calendar_service.get_calendar(calendar_id, db, principal)


@router.patch("/{calendar_id}", response_model=CalendarSchema)
async def update_calendar(
	calendar_id: TypeID,
	data: CalendarUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Calendar:
	"""update a calendar."""
	return await calendar_service.update_calendar(
		calendar_id,
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{calendar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_calendar(
	calendar_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a calendar."""
	await calendar_service.delete_calendar(
		calendar_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get(
	"/{calendar_id}/access-rules",
	response_model=list[AccessRuleResponse],
)
async def list_calendar_access_rules(
	calendar_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for a calendar."""
	return await access_rules_service.list_access_rules(
		ResourceType.CALENDAR,
		calendar_id,
		db,
		principal=principal,
	)


@router.put(
	"/{calendar_id}/access-rules",
	response_model=list[AccessRuleResponse],
)
async def set_calendar_access_rules(
	calendar_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for a calendar."""
	return await access_rules_service.set_access_rules(
		ResourceType.CALENDAR,
		calendar_id,
		rules,
		db,
		principal=principal,
	)


@router.get("/{calendar_id}/events", response_model=list[CalendarEventSchema])
async def list_calendar_events(
	calendar_id: TypeID,
	filters: Annotated[CalendarEventListFilters, Depends()],
	skip: int = 0,
	limit: int = Query(default=500, ge=1, le=1000),
	sort_by: CalendarEventSortBy = "start_at",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[CalendarEvent]:
	"""list events for a calendar accessible to the current user."""
	return await calendar_service.list_calendar_events(
		db,
		principal,
		calendar_id=calendar_id,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.post(
	"/{calendar_id}/events",
	response_model=CalendarEventSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_calendar_event(
	calendar_id: TypeID,
	data: CalendarEventCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> CalendarEvent:
	"""create a calendar event."""
	return await calendar_service.create_calendar_event(
		data,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)


@router.get("/{calendar_id}/events/{event_id}", response_model=CalendarEventSchema)
async def get_calendar_event(
	calendar_id: TypeID,
	event_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CalendarEvent:
	"""get a calendar event."""
	return await calendar_service.get_calendar_event(
		event_id,
		db,
		principal,
		calendar_id=calendar_id,
	)


@router.patch("/{calendar_id}/events/{event_id}", response_model=CalendarEventSchema)
async def update_calendar_event(
	calendar_id: TypeID,
	event_id: TypeID,
	data: CalendarEventUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> CalendarEvent:
	"""update a calendar event."""
	return await calendar_service.update_calendar_event(
		event_id,
		data,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)


@router.patch(
	"/{calendar_id}/events/{event_id}/occurrence",
	response_model=ScheduledItem,
)
async def edit_calendar_event_occurrence(
	calendar_id: TypeID,
	event_id: TypeID,
	data: CalendarOccurrenceEdit,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ScheduledItem:
	"""edit one calendar event occurrence."""
	return await calendar_service.edit_calendar_event_occurrence(
		event_id,
		data,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)


@router.patch(
	"/{calendar_id}/events/{event_id}/series/following",
	response_model=CalendarEventSchema,
)
async def edit_calendar_event_series(
	calendar_id: TypeID,
	event_id: TypeID,
	data: CalendarSeriesEdit,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> CalendarEvent:
	"""split and edit this/following event occurrences."""
	return await calendar_service.edit_calendar_event_series(
		event_id,
		data,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)


@router.post(
	"/{calendar_id}/events/{event_id}/occurrence/cancel",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_calendar_event_occurrence(
	calendar_id: TypeID,
	event_id: TypeID,
	data: CalendarOccurrenceCancel,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""cancel one calendar event occurrence."""
	await calendar_service.cancel_calendar_event_occurrence(
		event_id,
		data.original_occurrence_at,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)


@router.delete(
	"/{calendar_id}/events/{event_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_calendar_event(
	calendar_id: TypeID,
	event_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a calendar event series."""
	await calendar_service.delete_calendar_event(
		event_id,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)
