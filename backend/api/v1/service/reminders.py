"""service helpers for reminders and reminder lists."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.reminder import Reminder, ReminderList, ReminderStatus
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListCreate,
	ReminderListUpdate,
	ReminderListWithCounts,
	ReminderUpdate,
	ReminderWithSubtasks,
)
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.utils.typeid import TypeID


# sort column mappings
_REMINDER_LIST_SORT_COLUMNS = {
	"position": ReminderList.position,
	"name": ReminderList.name,
	"created_at": ReminderList.created_at,
	"updated_at": ReminderList.updated_at,
}
_REMINDER_SORT_COLUMNS = {
	"position": Reminder.position,
	"due_at": Reminder.due_at,
	"remind_at": Reminder.remind_at,
	"title": Reminder.title,
	"created_at": Reminder.created_at,
	"updated_at": Reminder.updated_at,
}


# --- ReminderList service ---


async def create_reminder_list(
	data: ReminderListCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> ReminderList:
	"""create a new reminder list."""
	reminder_list = ReminderList(
		owner_id=principal.user_id,
		**data.model_dump(exclude_unset=True),
	)
	session.add(reminder_list)
	await session.flush()
	await session.refresh(reminder_list)

	# emit reminder_list.created event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_CREATED,
		data={
			"list_id": str(reminder_list.id),
			"name": reminder_list.name,
			"icon": reminder_list.icon,
			"color": reminder_list.color,
			"position": reminder_list.position,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder_list


async def list_reminder_lists(
	session: AsyncSession,
	*,
	principal: Principal,
	include_counts: bool = False,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderListWithCounts]:
	"""list reminder lists, optionally with counts (single query)."""
	if not include_counts:
		stmt = select(ReminderList).where(ReminderList.owner_id == principal.user_id)
		stmt = apply_sort(
			stmt,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns=_REMINDER_LIST_SORT_COLUMNS,
		)
		stmt = stmt.offset(skip).limit(limit)
		result = await session.execute(stmt)
		return list(result.scalars().all())

	# single query with subquery for counts - fixes N+1
	counts_subq = (
		select(
			Reminder.list_id,
			func.count(Reminder.id).label("total"),
			func.sum(
				case((Reminder.status == ReminderStatus.PENDING, 1), else_=0)
			).label("pending"),
			func.sum(
				case((Reminder.status == ReminderStatus.COMPLETED, 1), else_=0)
			).label("completed"),
		)
		.where(Reminder.owner_id == principal.user_id)
		.where(Reminder.parent_id.is_(None))
		.group_by(Reminder.list_id)
		.subquery()
	)

	stmt = (
		select(
			ReminderList,
			func.coalesce(counts_subq.c.total, 0).label("total_count"),
			func.coalesce(counts_subq.c.pending, 0).label("pending_count"),
			func.coalesce(counts_subq.c.completed, 0).label("completed_count"),
		)
		.outerjoin(counts_subq, ReminderList.id == counts_subq.c.list_id)
		.where(ReminderList.owner_id == principal.user_id)
	)
	stmt = apply_sort(
		stmt, sort_by=sort_by, sort_dir=sort_dir, columns=_REMINDER_LIST_SORT_COLUMNS
	)
	stmt = stmt.offset(skip).limit(limit)

	result = await session.execute(stmt)
	rows = result.all()

	return [
		ReminderListWithCounts(
			**ReminderListWithCounts.model_validate(row.ReminderList).model_dump(
				exclude={"total_count", "pending_count", "completed_count"}
			),
			total_count=row.total_count,
			pending_count=row.pending_count,
			completed_count=row.completed_count,
		)
		for row in rows
	]


async def get_list_counts(
	session: AsyncSession,
	*,
	principal: Principal,
	list_id: TypeID | None = None,
) -> dict[str, int]:
	"""get counts for a specific list or default list (list_id=None)."""
	stmt = (
		select(
			func.count(Reminder.id).label("total"),
			func.sum(
				case((Reminder.status == ReminderStatus.PENDING, 1), else_=0)
			).label("pending"),
			func.sum(
				case((Reminder.status == ReminderStatus.COMPLETED, 1), else_=0)
			).label("completed"),
		)
		.where(Reminder.owner_id == principal.user_id)
		.where(Reminder.parent_id.is_(None))
	)
	if list_id is None:
		stmt = stmt.where(Reminder.list_id.is_(None))
	else:
		stmt = stmt.where(Reminder.list_id == list_id)

	result = await session.execute(stmt)
	row = result.one()
	return {
		"total_count": row.total or 0,
		"pending_count": int(row.pending or 0),
		"completed_count": int(row.completed or 0),
	}


async def get_reminder_list(
	list_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> ReminderList:
	"""get a reminder list by id."""
	reminder_list = await session.get(ReminderList, list_id)
	if not reminder_list or reminder_list.owner_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder list not found",
		)
	return reminder_list


async def update_reminder_list(
	list_id: TypeID,
	data: ReminderListUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> ReminderList:
	"""update a reminder list."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	for key, value in data.model_dump(exclude_unset=True).items():
		setattr(reminder_list, key, value)
	await session.flush()
	await session.refresh(reminder_list)

	# emit reminder_list.updated event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_UPDATED,
		data={
			"list_id": str(reminder_list.id),
			"name": reminder_list.name,
			"icon": reminder_list.icon,
			"color": reminder_list.color,
			"position": reminder_list.position,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder_list


async def delete_reminder_list(
	list_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""delete a reminder list and all its reminders."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	list_id_str = str(reminder_list.id)
	await session.delete(reminder_list)
	await session.flush()

	# emit reminder_list.deleted event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_DELETED,
		data={"list_id": list_id_str},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)


# --- Reminder service ---


async def create_reminder(
	data: ReminderCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Reminder:
	"""create a new reminder."""
	if data.list_id:
		await get_reminder_list(data.list_id, session, principal=principal)
	if data.parent_id:
		parent = await get_reminder(data.parent_id, session, principal=principal)
		if data.list_id and data.list_id != parent.list_id:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="subtask must belong to same list as parent",
			)
	reminder = Reminder(
		owner_id=principal.user_id,
		**data.model_dump(exclude_unset=True),
	)
	session.add(reminder)
	await session.flush()
	await session.refresh(reminder)

	# emit reminder.created event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_CREATED,
		data={
			"reminder_id": str(reminder.id),
			"list_id": str(reminder.list_id) if reminder.list_id else None,
			"title": reminder.title,
			"description": reminder.description,
			"status": reminder.status.value if reminder.status else None,
			"position": reminder.position,
			"due_at": reminder.due_at.isoformat() if reminder.due_at else None,
			"remind_at": reminder.remind_at.isoformat() if reminder.remind_at else None,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder


async def list_reminders(
	session: AsyncSession,
	*,
	principal: Principal,
	list_id: TypeID | None = None,
	status_filter: ReminderStatus | None = None,
	include_subtasks: bool = False,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderWithSubtasks]:
	"""list top-level reminders, optionally with subtasks eagerly loaded."""
	stmt = (
		select(Reminder)
		.where(Reminder.owner_id == principal.user_id)
		.where(Reminder.parent_id.is_(None))
	)

	if include_subtasks:
		stmt = stmt.options(selectinload(Reminder.subtasks))

	if list_id is None:
		stmt = stmt.where(Reminder.list_id.is_(None))
	else:
		stmt = stmt.where(Reminder.list_id == list_id)

	if status_filter is not None:
		stmt = stmt.where(Reminder.status == status_filter)

	stmt = apply_sort(
		stmt, sort_by=sort_by, sort_dir=sort_dir, columns=_REMINDER_SORT_COLUMNS
	)
	stmt = stmt.offset(skip).limit(limit)

	result = await session.execute(stmt)
	return [ReminderWithSubtasks.model_validate(r) for r in result.scalars().all()]


async def get_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	with_subtasks: bool = False,
) -> Reminder:
	"""get a reminder by id."""
	if with_subtasks:
		stmt = (
			select(Reminder)
			.options(selectinload(Reminder.subtasks))
			.where(Reminder.id == reminder_id)
		)
		result = await session.execute(stmt)
		reminder = result.scalars().first()
	else:
		reminder = await session.get(Reminder, reminder_id)

	if not reminder or reminder.owner_id != principal.user_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder not found",
		)
	return reminder


async def update_reminder(
	reminder_id: TypeID,
	data: ReminderUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Reminder:
	"""update a reminder."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	update_data = data.model_dump(exclude_unset=True)
	previous_list_id = reminder.list_id

	# handle status changes
	if "status" in update_data:
		if (
			update_data["status"] == ReminderStatus.COMPLETED
			and reminder.status != ReminderStatus.COMPLETED
		):
			update_data["completed_at"] = datetime.now(UTC)
		elif update_data["status"] == ReminderStatus.PENDING:
			update_data["completed_at"] = None

	if "list_id" in update_data and update_data["list_id"] is not None:
		await get_reminder_list(update_data["list_id"], session, principal=principal)

	for key, value in update_data.items():
		setattr(reminder, key, value)

	await session.flush()
	await session.refresh(reminder)

	# emit reminder.updated event

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data={
			"reminder_id": str(reminder.id),
			"list_id": str(reminder.list_id) if reminder.list_id else None,
			"previous_list_id": str(previous_list_id) if previous_list_id else None,
			"title": reminder.title,
			"description": reminder.description,
			"status": reminder.status.value if reminder.status else None,
			"position": reminder.position,
			"due_at": reminder.due_at.isoformat() if reminder.due_at else None,
			"remind_at": reminder.remind_at.isoformat() if reminder.remind_at else None,
			"completed_at": (
				reminder.completed_at.isoformat() if reminder.completed_at else None
			),
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder


async def complete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	cascade: bool = False,
) -> Reminder:
	"""mark a reminder as completed, optionally cascading to subtasks."""
	reminder = await get_reminder(
		reminder_id, session, principal=principal, with_subtasks=cascade
	)
	now = datetime.now(UTC)

	reminder.status = ReminderStatus.COMPLETED
	reminder.completed_at = now

	if cascade and reminder.subtasks:
		for subtask in reminder.subtasks:
			if subtask.status != ReminderStatus.COMPLETED:
				subtask.status = ReminderStatus.COMPLETED
				subtask.completed_at = now

	await session.flush()
	await session.refresh(reminder)

	# emit reminder.completed event
	completed_at = reminder.completed_at
	completed_iso = completed_at.isoformat() if completed_at else None
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_COMPLETED,
		data={
			"reminder_id": str(reminder.id),
			"list_id": str(reminder.list_id) if reminder.list_id else None,
			"title": reminder.title,
			"status": reminder.status.value,
			"completed_at": completed_iso,
			"cascade": cascade,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder


async def delete_reminder(
	reminder_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""delete a reminder and its subtasks."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	reminder_id_str = str(reminder.id)
	list_id_str = str(reminder.list_id) if reminder.list_id else None
	await session.delete(reminder)
	await session.flush()

	# emit reminder.deleted event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_DELETED,
		data={
			"reminder_id": reminder_id_str,
			"list_id": list_id_str,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)


async def move_reminder(
	reminder_id: TypeID,
	target_list_id: TypeID | None,
	session: AsyncSession,
	*,
	principal: Principal,
	position: float | None = None,
) -> Reminder:
	"""move a reminder to a different list (or default list if null)."""
	reminder = await get_reminder(reminder_id, session, principal=principal)
	previous_list_id = reminder.list_id

	if target_list_id is not None:
		await get_reminder_list(target_list_id, session, principal=principal)

	reminder.list_id = target_list_id
	if position is not None:
		reminder.position = position

	await session.flush()
	await session.refresh(reminder)

	# emit reminder.updated event with move info
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_UPDATED,
		data={
			"reminder_id": str(reminder.id),
			"list_id": str(reminder.list_id) if reminder.list_id else None,
			"previous_list_id": str(previous_list_id) if previous_list_id else None,
			"title": reminder.title,
			"status": reminder.status.value if reminder.status else None,
			"position": reminder.position,
		},
		user_id=principal.user_id,
	)
	await event_service.publish_event(session, event=event)

	return reminder
