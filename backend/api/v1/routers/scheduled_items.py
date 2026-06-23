"""scheduled item routers."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.schemas.scheduled_item import ScheduledItem, ScheduledItemListFilters
from api.settings import settings
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.calendar.events import list_calendar_scheduled_items
from api.v1.service.reminders.core import list_reminder_scheduled_items


router = APIRouter(prefix="/scheduled-items", tags=["scheduled-items"])


@router.get("", response_model=list[ScheduledItem])
async def list_scheduled_items(
	filters: Annotated[ScheduledItemListFilters, Depends()],
	limit: int = Query(default=2000, ge=1, le=5000),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ScheduledItem]:
	"""list merged scheduled instances from calendar and reminder domains."""
	if filters.end_at <= filters.start_at:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="end time must be after start time",
		)
	if filters.end_at - filters.start_at > timedelta(
		days=settings.limits.max_scheduled_items_window_days,
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="scheduled item window cannot exceed"
			f" {settings.limits.max_scheduled_items_window_days} days",
		)

	items = [
		*(
			await list_calendar_scheduled_items(
				db,
				principal,
				filters.start_at,
				filters.end_at,
			)
		),
		*(
			await list_reminder_scheduled_items(
				db,
				principal,
				filters.start_at,
				filters.end_at,
				include_completed=filters.include_completed,
			)
		),
	]
	items.sort(
		key=lambda item: (item.effective_start_at, item.kind, str(item.parent_id))
	)
	return items[:limit]
