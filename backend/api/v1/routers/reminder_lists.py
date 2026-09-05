"""nested reminder list routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.reminder import Reminder, ReminderList
from api.permissions import ActionPermission, ResourceType
from api.schemas.reminder import (
	Reminder as ReminderSchema,
)
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListCreate,
	ReminderListFilters,
	ReminderListItemFilters,
	ReminderListSortBy,
	ReminderListUpdate,
	ReminderListWithCounts,
	ReminderSearchFilters,
	ReminderSortBy,
	ReminderUpdate,
	ReminderWithSubtasks,
)
from api.schemas.reminder import (
	ReminderList as ReminderListSchema,
)
from api.schemas.scheduled_item import (
	ReminderOccurrenceComplete,
	ReminderSeriesEdit,
	ScheduledItem,
)
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_permission
from api.v1.service.events import SessionId
from api.v1.service.reminders import (
	complete_reminder as complete_reminder_service,
)
from api.v1.service.reminders import (
	complete_reminder_occurrence as complete_reminder_occurrence_service,
)
from api.v1.service.reminders import (
	count_reminder_lists as count_reminder_lists_service,
)
from api.v1.service.reminders import (
	create_reminder as create_reminder_service,
)
from api.v1.service.reminders import (
	create_reminder_list as create_reminder_list_service,
)
from api.v1.service.reminders import (
	delete_reminder as delete_reminder_service,
)
from api.v1.service.reminders import (
	delete_reminder_list as delete_reminder_list_service,
)
from api.v1.service.reminders import (
	edit_reminder_series as edit_reminder_series_service,
)
from api.v1.service.reminders import (
	get_list_counts,
	search_reminders,
	vectorize_reminders,
)
from api.v1.service.reminders import (
	get_reminder as get_reminder_service,
)
from api.v1.service.reminders import (
	get_reminder_list as get_reminder_list_service,
)
from api.v1.service.reminders import (
	list_reminder_lists as list_reminder_lists_service,
)
from api.v1.service.reminders import (
	list_reminders as list_reminders_service,
)
from api.v1.service.reminders import (
	update_reminder as update_reminder_service,
)
from api.v1.service.reminders import (
	update_reminder_list as update_reminder_list_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/reminder-lists", tags=["reminder-lists"])
router.include_router(
	create_resource_access_router(ResourceType.REMINDER_LIST, "list_id")
)
reminders_router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderListWithCounts])
async def list_reminder_lists(
	filters: Annotated[ReminderListFilters, Depends()],
	include_counts: bool = False,
	skip: int = 0,
	limit: int = Query(default=50, ge=1, le=500),
	sort_by: ReminderListSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ReminderListWithCounts]:
	"""list reminder lists accessible to the current user."""
	return await list_reminder_lists_service(
		db,
		principal=principal,
		include_counts=include_counts,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_reminder_lists(
	filters: Annotated[ReminderListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count reminder lists accessible to the current user."""
	return await count_reminder_lists_service(db, principal=principal, filters=filters)


@router.post("", response_model=ReminderListSchema, status_code=status.HTTP_201_CREATED)
async def create_reminder_list(
	data: ReminderListCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ReminderList:
	"""create a reminder list."""
	return await create_reminder_list_service(
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/search", response_model=Page[ReminderSchema])
async def search_reminder_lists(
	filters: Annotated[ReminderSearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[ReminderSchema]:
	"""search reminders, returning relevance-ordered reminders."""
	scored = await search_reminders(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[ReminderSchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@reminders_router.post("/revectorize")
async def revectorize_reminders(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all reminders into qdrant. reminders operators only."""
	require_permission(principal, ActionPermission.REMINDERS_MANAGE)
	count = await vectorize_reminders(db)
	return {"vectorized": count}


@router.get("/{list_id}", response_model=ReminderListSchema)
async def get_reminder_list(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ReminderList:
	"""get a reminder list."""
	return await get_reminder_list_service(list_id, db, principal=principal)


@router.patch("/{list_id}", response_model=ReminderListSchema)
async def update_reminder_list(
	list_id: TypeID,
	data: ReminderListUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ReminderList:
	"""update a reminder list."""
	return await update_reminder_list_service(
		list_id,
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder_list(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a reminder list."""
	await delete_reminder_list_service(
		list_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/{list_id}/counts")
async def get_reminder_list_counts(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""get reminder counts for a list."""
	return await get_list_counts(
		db,
		principal=principal,
		list_id=list_id,
	)


@router.get("/{list_id}/reminders", response_model=list[ReminderWithSubtasks])
async def list_reminders(
	list_id: TypeID,
	filters: Annotated[ReminderListItemFilters, Depends()],
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = Query(default=100, ge=1, le=500),
	sort_by: ReminderSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ReminderWithSubtasks]:
	"""list reminders in a reminder list."""
	return await list_reminders_service(
		db,
		principal=principal,
		list_id=list_id,
		filters=filters,
		include_subtasks=include_subtasks,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.post(
	"/{list_id}/reminders",
	response_model=ReminderSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_reminder(
	list_id: TypeID,
	data: ReminderCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""create a reminder in a reminder list."""
	if data.list_id is not None and data.list_id != list_id:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="list id does not match route",
		)
	return await create_reminder_service(
		data.model_copy(update={"list_id": list_id}),
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("/{list_id}/reminders/{reminder_id}", response_model=ReminderWithSubtasks)
async def get_reminder(
	list_id: TypeID,
	reminder_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Reminder:
	"""get a reminder in a reminder list."""
	reminder = await get_reminder_service(
		reminder_id,
		db,
		principal=principal,
		with_subtasks=True,
	)
	_ensure_reminder_in_list(reminder, list_id)
	return reminder


@router.patch("/{list_id}/reminders/{reminder_id}", response_model=ReminderSchema)
async def update_reminder(
	list_id: TypeID,
	reminder_id: TypeID,
	data: ReminderUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""update a reminder in a reminder list."""
	reminder = await get_reminder_service(reminder_id, db, principal=principal)
	_ensure_reminder_in_list(reminder, list_id)
	return await update_reminder_service(
		reminder_id,
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post(
	"/{list_id}/reminders/{reminder_id}/complete",
	response_model=ReminderSchema,
)
async def complete_reminder(
	list_id: TypeID,
	reminder_id: TypeID,
	cascade: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""complete a non-recurring reminder in a reminder list."""
	reminder = await get_reminder_service(reminder_id, db, principal=principal)
	_ensure_reminder_in_list(reminder, list_id)
	return await complete_reminder_service(
		reminder_id,
		db,
		principal=principal,
		cascade=cascade,
		origin_session_id=x_session_id,
	)


@router.post(
	"/{list_id}/reminders/{reminder_id}/occurrence/complete",
	response_model=ScheduledItem,
)
async def complete_reminder_occurrence(
	list_id: TypeID,
	reminder_id: TypeID,
	data: ReminderOccurrenceComplete,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ScheduledItem:
	"""complete one recurring reminder occurrence."""
	reminder = await get_reminder_service(reminder_id, db, principal=principal)
	_ensure_reminder_in_list(reminder, list_id)
	return await complete_reminder_occurrence_service(
		reminder_id,
		data.original_occurrence_at,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.patch(
	"/{list_id}/reminders/{reminder_id}/series/following",
	response_model=ReminderSchema,
)
async def edit_reminder_series(
	list_id: TypeID,
	reminder_id: TypeID,
	data: ReminderSeriesEdit,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""split and edit this/following reminder occurrences."""
	reminder = await get_reminder_service(reminder_id, db, principal=principal)
	_ensure_reminder_in_list(reminder, list_id)
	return await edit_reminder_series_service(
		reminder_id,
		data,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete(
	"/{list_id}/reminders/{reminder_id}",
	status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_reminder(
	list_id: TypeID,
	reminder_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a reminder series in a reminder list."""
	reminder = await get_reminder_service(reminder_id, db, principal=principal)
	_ensure_reminder_in_list(reminder, list_id)
	await delete_reminder_service(
		reminder_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


def _ensure_reminder_in_list(reminder: Reminder, list_id: TypeID) -> None:
	if reminder.list_id == list_id:
		return
	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND,
		detail="reminder not found",
	)
