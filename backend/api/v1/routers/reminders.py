"""reminder routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.reminder import Reminder, ReminderList, ReminderStatus
from api.schemas.reminder import (
	Reminder as ReminderSchema,
)
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListCreate,
	ReminderListUpdate,
	ReminderListWithCounts,
	ReminderUpdate,
	ReminderWithSubtasks,
)
from api.schemas.reminder import (
	ReminderList as ReminderListSchema,
)
from api.schemas.search import CursorPage, SearchMode, SearchParams, SearchResultItem
from api.v1.service import reminders as reminder_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.events import SessionId
from api.v1.service.sorting import SortDir
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/reminders", tags=["reminders"])

ReminderSortBy = Literal["position", "due_at", "created_at", "updated_at", "title"]
ListSortBy = Literal["position", "name", "created_at", "updated_at"]


# --- ReminderList endpoints ---


@router.post(
	"/lists",
	response_model=ReminderListSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_reminder_list(
	data: ReminderListCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ReminderList:
	"""create a new reminder list."""
	return await reminder_service.create_reminder_list(
		data, db, principal=principal, origin_session_id=x_session_id
	)


@router.get("/lists")
async def list_reminder_lists(
	include_counts: bool = False,
	skip: int = 0,
	limit: int = 50,
	sort_by: ListSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ReminderListWithCounts]:
	"""list all reminder lists, optionally with counts."""
	return await reminder_service.list_reminder_lists(
		db,
		principal=principal,
		include_counts=include_counts,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/lists/{list_id}", response_model=ReminderListSchema)
async def get_reminder_list(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> ReminderList:
	"""get a reminder list by id."""
	return await reminder_service.get_reminder_list(list_id, db, principal=principal)


@router.get("/lists/{list_id}/counts")
async def get_reminder_list_counts(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""get reminder counts for a specific list."""
	return await reminder_service.get_list_counts(
		db, principal=principal, list_id=list_id
	)


@router.get("/counts")
async def get_default_reminder_list_counts(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""get reminder counts for the default list (reminders without a list)."""
	return await reminder_service.get_list_counts(
		db, principal=principal, list_id=None
	)


@router.patch("/lists/{list_id}", response_model=ReminderListSchema)
async def update_reminder_list(
	list_id: TypeID,
	data: ReminderListUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> ReminderList:
	"""update a reminder list."""
	return await reminder_service.update_reminder_list(
		list_id, data, db, principal=principal, origin_session_id=x_session_id
	)


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder_list(
	list_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a reminder list and all its reminders."""
	await reminder_service.delete_reminder_list(
		list_id, db, principal=principal, origin_session_id=x_session_id
	)


# --- Reminder endpoints ---


@router.post("", response_model=ReminderSchema, status_code=status.HTTP_201_CREATED)
async def create_reminder(
	data: ReminderCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""create a new reminder."""
	return await reminder_service.create_reminder(
		data, db, principal=principal, origin_session_id=x_session_id
	)


@router.get("")
async def list_reminders(
	list_id: TypeID | None = None,
	status_filter: ReminderStatus | None = None,
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = 100,
	sort_by: ReminderSortBy = "position",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[ReminderWithSubtasks]:
	"""
	list reminders. omit list_id for default list.

	include_subtasks eagerly loads subtasks.
	"""
	return await reminder_service.list_reminders(
		db,
		principal=principal,
		list_id=list_id,
		status_filter=status_filter,
		include_subtasks=include_subtasks,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/search", response_model=CursorPage[SearchResultItem])
async def search_reminders(
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	cursor: str | None = Query(default=None),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CursorPage[SearchResultItem]:
	"""search reminders with cursor-based pagination."""
	return await reminder_service.search_reminders(
		q,
		db,
		principal=principal,
		limit=limit,
		cursor=cursor,
		search_params=SearchParams(mode=mode),
	)


@router.post("/revectorize")
async def revectorize_reminders(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all reminders into qdrant. admin only."""
	require_admin(principal)
	count = await reminder_service.vectorize_all_reminders(db)
	return {"vectorized": count}


@router.get("/{reminder_id}", response_model=ReminderWithSubtasks)
async def get_reminder(
	reminder_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Reminder:
	"""get a reminder by id with subtasks."""
	return await reminder_service.get_reminder(
		reminder_id, db, principal=principal, with_subtasks=True
	)


@router.patch("/{reminder_id}", response_model=ReminderSchema)
async def update_reminder(
	reminder_id: TypeID,
	data: ReminderUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""update a reminder."""
	return await reminder_service.update_reminder(
		reminder_id, data, db, principal=principal, origin_session_id=x_session_id
	)


@router.post("/{reminder_id}/complete", response_model=ReminderSchema)
async def complete_reminder(
	reminder_id: TypeID,
	cascade: bool = False,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""mark a reminder as completed, optionally cascading to subtasks."""
	return await reminder_service.complete_reminder(
		reminder_id,
		db,
		principal=principal,
		cascade=cascade,
		origin_session_id=x_session_id,
	)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
	reminder_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a reminder."""
	await reminder_service.delete_reminder(
		reminder_id, db, principal=principal, origin_session_id=x_session_id
	)


@router.post("/{reminder_id}/move", response_model=ReminderSchema)
async def move_reminder(
	reminder_id: TypeID,
	target_list_id: TypeID | None = None,
	position: float | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Reminder:
	"""move a reminder to a different list (or default list if null)."""
	return await reminder_service.move_reminder(
		reminder_id,
		target_list_id,
		db,
		principal=principal,
		position=position,
		origin_session_id=x_session_id,
	)
