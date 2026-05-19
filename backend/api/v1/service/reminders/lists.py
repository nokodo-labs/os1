"""reminder list service helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.reminder import Reminder, ReminderList, ReminderStatus
from api.permissions import ResourceType
from api.schemas.reminder import ReminderList as ReminderListOut
from api.schemas.reminder import (
	ReminderListCreate,
	ReminderListFilters,
	ReminderListUpdate,
	ReminderListWithCounts,
)
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	require_permission,
	require_project_access,
	require_resource_access,
	resource_access_predicate,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.projects import invalidate_project_payload_caches, load_projects
from api.v1.service.reminders.cache import (
	invalidate_reminder_list_scheduled_items,
)
from api.v1.service.reminders.search import REMINDER_SPEC, vectorize_reminders_for_list
from api.v1.service.vectorize import remove_vectorized_resource
from api.v1.tasks.reminders import cancel_reminder_notifications
from nokodo_ai.utils.typeid import TypeID


_DEFAULT_REMINDER_LIST_NAME = "personal"

_REMINDER_LIST_SORT_COLUMNS = {
	"position": ReminderList.position,
	"name": ReminderList.name,
	"created_at": ReminderList.created_at,
	"updated_at": ReminderList.updated_at,
}


async def _clear_default_reminder_lists(
	session: AsyncSession,
	principal: Principal,
	except_id: TypeID | None = None,
	owner_id: TypeID | None = None,
) -> None:
	target_owner_id = owner_id if owner_id is not None else principal.user_id
	stmt = select(ReminderList).where(
		ReminderList.owner_id == target_owner_id,
		ReminderList.is_default.is_(True),
	)
	if except_id is not None:
		stmt = stmt.where(ReminderList.id != except_id)
	result = await session.execute(stmt)
	for reminder_list in result.scalars().all():
		reminder_list.is_default = False


async def get_or_create_default_reminder_list(
	session: AsyncSession,
	principal: Principal,
) -> ReminderList:
	"""get or create the principal's default reminder list."""
	stmt = (
		select(ReminderList)
		.where(
			ReminderList.owner_id == principal.user_id,
			ReminderList.is_default.is_(True),
		)
		.order_by(ReminderList.created_at.asc())
	)
	result = await session.execute(stmt)
	reminder_list = result.scalars().first()
	if reminder_list is not None:
		return reminder_list

	reminder_list = ReminderList(
		owner_id=principal.user_id,
		name=_DEFAULT_REMINDER_LIST_NAME,
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=True,
	)
	session.add(reminder_list)
	await session.flush()
	return reminder_list


async def create_reminder_list(
	data: ReminderListCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ReminderList:
	"""create a new reminder list."""
	require_permission(principal, "reminders:create")
	for pid in data.project_ids:
		await require_project_access(
			pid,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	if data.is_default:
		await _clear_default_reminder_lists(session, principal)
	reminder_list = ReminderList(
		owner_id=principal.user_id,
		**data.model_dump(exclude_unset=True, by_alias=True, exclude={"project_ids"}),
		projects=(
			await load_projects(data.project_ids, session, principal)
			if data.project_ids
			else []
		),
	)
	session.add(reminder_list)
	await session.flush()

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_CREATED,
		data=ReminderListOut.model_validate(reminder_list).model_dump(mode="json"),
		user_id=principal.user_id,
		reminder_list_id=reminder_list.id,
	)
	await event_service.persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await invalidate_project_payload_caches(set(data.project_ids))

	return reminder_list


async def list_reminder_lists(
	session: AsyncSession,
	principal: Principal,
	filters: ReminderListFilters | None = None,
	include_counts: bool = False,
	skip: int = 0,
	limit: int = 50,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[ReminderListWithCounts]:
	"""list reminder lists, optionally with counts."""
	await get_or_create_default_reminder_list(session, principal)
	list_filters = filters or ReminderListFilters()
	if not include_counts:
		stmt = select(ReminderList).where(
			resource_access_predicate(principal, ResourceType.REMINDER_LIST),
		)
		stmt = _apply_reminder_list_filters(stmt, list_filters)
		stmt = apply_sort(
			stmt,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns=_REMINDER_LIST_SORT_COLUMNS,
		)
		stmt = (
			stmt.offset(skip)
			.limit(limit)
			.options(
				selectinload(ReminderList.projects),
			)
		)
		result = await session.execute(stmt)
		no_count_lists = result.scalars().all()
		return [ReminderListWithCounts.model_validate(rl) for rl in no_count_lists]

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
		.where(Reminder.parent_id.is_(None))
		.group_by(Reminder.list_id)
		.subquery()
	)

	counts_stmt = (
		select(
			ReminderList,
			func.coalesce(counts_subq.c.total, 0).label("total_count"),
			func.coalesce(counts_subq.c.pending, 0).label("pending_count"),
			func.coalesce(counts_subq.c.completed, 0).label("completed_count"),
		)
		.outerjoin(counts_subq, ReminderList.id == counts_subq.c.list_id)
		.where(
			resource_access_predicate(principal, ResourceType.REMINDER_LIST),
		)
	)
	counts_stmt = _apply_reminder_list_filters(counts_stmt, list_filters)
	counts_stmt = apply_sort(
		counts_stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns=_REMINDER_LIST_SORT_COLUMNS,
	)
	counts_stmt = (
		counts_stmt.offset(skip)
		.limit(limit)
		.options(selectinload(ReminderList.projects))
	)

	result = await session.execute(counts_stmt)
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


async def count_reminder_lists(
	session: AsyncSession,
	principal: Principal,
	filters: ReminderListFilters | None = None,
) -> int:
	"""count reminder lists accessible to the principal."""
	await get_or_create_default_reminder_list(session, principal)
	list_filters = filters or ReminderListFilters()
	stmt = (
		select(func.count())
		.select_from(ReminderList)
		.where(
			resource_access_predicate(principal, ResourceType.REMINDER_LIST),
		)
	)
	stmt = _apply_reminder_list_filters(stmt, list_filters)
	return await session.scalar(stmt) or 0


def _apply_reminder_list_filters(
	stmt: Select,
	filters: ReminderListFilters,
) -> Select:
	"""apply reminder-list list/count filters."""
	if filters.owner_id is not None:
		stmt = stmt.where(ReminderList.owner_id == filters.owner_id)
	return stmt


async def get_list_counts(
	session: AsyncSession,
	principal: Principal,
	list_id: TypeID,
) -> dict[str, int]:
	"""get counts for a specific reminder list."""
	await get_reminder_list(list_id, session, principal=principal)
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
		.where(Reminder.parent_id.is_(None))
		.where(Reminder.list_id == list_id)
	)

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
	principal: Principal,
) -> ReminderList:
	"""get a reminder list by id."""
	result = await session.execute(
		select(ReminderList)
		.where(ReminderList.id == list_id)
		.options(selectinload(ReminderList.projects))
	)
	reminder_list = result.scalars().one_or_none()
	if not reminder_list:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="reminder list not found",
		)
	await require_resource_access(
		list_id,
		session,
		principal,
		ResourceType.REMINDER_LIST,
		owner_id=reminder_list.owner_id,
	)
	return reminder_list


async def update_reminder_list(
	list_id: TypeID,
	data: ReminderListUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ReminderList:
	"""update a reminder list."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	if "is_default" in data.model_fields_set and data.is_default is True:
		await _clear_default_reminder_lists(
			session,
			principal,
			except_id=reminder_list.id,
			owner_id=reminder_list.owner_id,
		)
	update_data = data.model_dump(exclude_unset=True, by_alias=True)
	new_project_ids: list[TypeID] | None = update_data.pop("project_ids", None)
	changed_project_ids: set[TypeID] = set()
	if new_project_ids is not None:
		old_project_ids = {project.id for project in reminder_list.projects}
		for pid in new_project_ids:
			await require_project_access(
				pid,
				session,
				principal,
				required_level=AccessLevel.EDITOR,
			)
		reminder_list.projects = await load_projects(
			new_project_ids, session, principal
		)
		changed_project_ids = old_project_ids | set(new_project_ids)
	for key, value in update_data.items():
		setattr(reminder_list, key, value)
	await session.flush()
	await session.refresh(reminder_list, attribute_names=["updated_at"])

	event_data = data.model_dump(mode="json", exclude_unset=True)
	event_data["id"] = str(reminder_list.id)
	event_data["updated_at"] = reminder_list.updated_at.isoformat()
	if changed_project_ids:
		event_data["affected_project_ids"] = [
			str(project_id) for project_id in changed_project_ids
		]
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_UPDATED,
		data=event_data,
		user_id=principal.user_id,
		reminder_list_id=reminder_list.id,
	)
	await event_service.persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await invalidate_reminder_list_scheduled_items(reminder_list.id)
	if changed_project_ids:
		await invalidate_accessible_users_for_resource(
			ResourceType.REMINDER_LIST, list_id, session
		)
	await invalidate_project_payload_caches(changed_project_ids)

	_list_search_fields = {"name", "description"}
	if _list_search_fields & update_data.keys():
		await vectorize_reminders_for_list(list_id, session)

	return reminder_list


async def delete_reminder_list(
	list_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a reminder list and all its reminders."""
	reminder_list = await get_reminder_list(list_id, session, principal=principal)
	if reminder_list.is_default:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="default reminder list cannot be deleted",
		)
	project_ids = {project.id for project in reminder_list.projects}
	list_id_str = reminder_list.id
	result = await session.execute(
		select(Reminder).where(Reminder.list_id == reminder_list.id)
	)
	reminders = list(result.scalars().all())
	for reminder in reminders:
		await remove_vectorized_resource(
			REMINDER_SPEC,
			resource_id=str(reminder.id),
			session=session,
		)
		await cancel_reminder_notifications(reminder.id)

	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.REMINDER_LIST_DELETED,
		data={
			"id": list_id_str,
			"project_ids": [str(project_id) for project_id in project_ids],
			"affected_project_ids": [str(project_id) for project_id in project_ids],
		},
		user_id=principal.user_id,
		reminder_list_id=reminder_list.id,
	)
	await event_service.persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)
	await invalidate_reminder_list_scheduled_items(reminder_list.id)
	await invalidate_accessible_users_for_resource(
		ResourceType.REMINDER_LIST, list_id, session
	)
	await invalidate_project_payload_caches(project_ids)
	await session.delete(reminder_list)
	await session.flush()
