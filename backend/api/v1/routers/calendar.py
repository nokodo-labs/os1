"""calendar routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.calendar import Calendar, CalendarEvent
from api.permissions import ActionPermission, ResourceType
from api.schemas.calendar import (
	Calendar as CalendarSchema,
)
from api.schemas.calendar import (
	CalendarCreate,
	CalendarEventCreate,
	CalendarEventListFilters,
	CalendarEventSearchFilters,
	CalendarEventSortBy,
	CalendarEventUpdate,
	CalendarListFilters,
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
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_permission
from api.v1.service.calendar import (
	cancel_calendar_event_occurrence as cancel_calendar_event_occurrence_service,
)
from api.v1.service.calendar import (
	count_calendars as count_calendars_service,
)
from api.v1.service.calendar import (
	create_calendar as create_calendar_service,
)
from api.v1.service.calendar import (
	create_calendar_event as create_calendar_event_service,
)
from api.v1.service.calendar import (
	delete_calendar as delete_calendar_service,
)
from api.v1.service.calendar import (
	delete_calendar_event as delete_calendar_event_service,
)
from api.v1.service.calendar import (
	edit_calendar_event_occurrence as edit_calendar_event_occurrence_service,
)
from api.v1.service.calendar import (
	edit_calendar_event_series as edit_calendar_event_series_service,
)
from api.v1.service.calendar import (
	get_calendar as get_calendar_service,
)
from api.v1.service.calendar import (
	get_calendar_event as get_calendar_event_service,
)
from api.v1.service.calendar import (
	list_calendar_events as list_calendar_events_service,
)
from api.v1.service.calendar import (
	list_calendars as list_calendars_service,
)
from api.v1.service.calendar import (
	search_calendar_events,
	vectorize_calendar_events,
)
from api.v1.service.calendar import (
	update_calendar as update_calendar_service,
)
from api.v1.service.calendar import (
	update_calendar_event as update_calendar_event_service,
)
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/calendars", tags=["calendars"])
router.include_router(
	create_resource_access_router(ResourceType.CALENDAR, "calendar_id")
)


@router.get("", response_model=list[CalendarSchema])
async def list_calendars(
	filters: Annotated[CalendarListFilters, Depends()],
	skip: int = 0,
	limit: int = Query(default=100, ge=1, le=500),
	sort_by: CalendarSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Calendar]:
	"""list calendars accessible to the current user."""
	return await list_calendars_service(
		db,
		principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_calendars(
	filters: Annotated[CalendarListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count calendars accessible to the current user."""
	return await count_calendars_service(db, principal, filters=filters)


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
	return await create_calendar_service(
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/search", response_model=Page[CalendarEventSchema])
async def search_calendars(
	filters: Annotated[CalendarEventSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[CalendarEventSchema]:
	"""search calendar events returning ranked event objects."""
	scored = await search_calendar_events(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[CalendarEventSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.post("/events/revectorize")
async def revectorize_calendar_events(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all calendar events into qdrant. calendar operators only."""
	require_permission(principal, ActionPermission.CALENDAR_MANAGE)
	count = await vectorize_calendar_events(db)
	return {"vectorized": count}


@router.get("/{calendar_id}", response_model=CalendarSchema)
async def get_calendar(
	calendar_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Calendar:
	"""get a calendar."""
	return await get_calendar_service(calendar_id, db, principal)


@router.patch("/{calendar_id}", response_model=CalendarSchema)
async def update_calendar(
	calendar_id: TypeID,
	data: CalendarUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Calendar:
	"""update a calendar."""
	return await update_calendar_service(
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
	await delete_calendar_service(
		calendar_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
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
	return await list_calendar_events_service(
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
	return await create_calendar_event_service(
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
	return await get_calendar_event_service(
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
	return await update_calendar_event_service(
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
	return await edit_calendar_event_occurrence_service(
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
	return await edit_calendar_event_series_service(
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
	await cancel_calendar_event_occurrence_service(
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
	await delete_calendar_event_service(
		event_id,
		db,
		principal=principal,
		calendar_id=calendar_id,
		origin_session_id=x_session_id,
	)
