"""calendar CRUD service helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from api.models.access_rule import AccessLevel
from api.models.calendar import Calendar, CalendarEvent
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.calendar import CalendarCreate, CalendarListFilters, CalendarUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	invalidate_accessible_users_for_resource,
	require_permission,
	resource_access_predicate,
)
from api.v1.service.calendar.cache import invalidate_calendar_scheduled_items
from api.v1.service.calendar.common import (
	CALENDAR_CREATE_PERMISSION,
	clear_default_calendars,
	get_accessible_calendar,
	get_or_create_default_calendar,
	load_calendar_projects,
	publish_calendar,
	publish_calendar_event,
)
from api.v1.service.calendar.search import CALENDAR_EVENT_SPEC
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.projects import invalidate_project_payload_caches
from api.v1.service.vectorize import remove_vectorized_resource
from api.v1.tasks.calendar import cancel_calendar_event_notifications
from nokodo_ai.utils.typeid import TypeID


_CALENDAR_SORT_COLUMNS = {
	"name": Calendar.name,
	"position": Calendar.position,
	"created_at": Calendar.created_at,
	"updated_at": Calendar.updated_at,
}


async def list_calendars(
	session: AsyncSession,
	principal: Principal,
	filters: CalendarListFilters | None = None,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "position",
	sort_dir: SortDir = "asc",
) -> list[Calendar]:
	"""list calendars accessible to the principal."""
	await get_or_create_default_calendar(session, principal)
	calendar_filters = filters or CalendarListFilters()
	stmt = (
		select(Calendar)
		.where(resource_access_predicate(principal, ResourceType.CALENDAR))
		.options(selectinload(Calendar.projects))
	)
	stmt = _apply_calendar_filters(stmt, calendar_filters)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns=_CALENDAR_SORT_COLUMNS,
		tie_breaker=Calendar.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def count_calendars(
	session: AsyncSession,
	principal: Principal,
	filters: CalendarListFilters | None = None,
) -> int:
	"""count calendars accessible to the principal."""
	await get_or_create_default_calendar(session, principal)
	calendar_filters = filters or CalendarListFilters()
	stmt = (
		select(func.count())
		.select_from(Calendar)
		.where(
			resource_access_predicate(principal, ResourceType.CALENDAR),
		)
	)
	stmt = _apply_calendar_filters(stmt, calendar_filters)
	return await session.scalar(stmt) or 0


def _apply_calendar_filters(stmt: Select, filters: CalendarListFilters) -> Select:
	"""apply calendar list/count filters."""
	if filters.owner_id is not None:
		stmt = stmt.where(Calendar.owner_id == filters.owner_id)
	return stmt


async def create_calendar(
	data: CalendarCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Calendar:
	"""create a calendar."""
	require_permission(principal, CALENDAR_CREATE_PERMISSION)
	projects = await load_calendar_projects(data.project_ids, session, principal)
	if data.is_default:
		await clear_default_calendars(session, principal)
	calendar = Calendar(
		owner_id=principal.user_id,
		**data.model_dump(
			exclude_unset=True,
			by_alias=True,
			exclude={"project_ids"},
		),
		projects=projects,
	)
	session.add(calendar)
	await session.flush()
	await session.refresh(calendar)
	await session.refresh(calendar, attribute_names=["projects"])
	await publish_calendar(
		session,
		calendar=calendar,
		event_type=EventType.CALENDAR_CREATED,
		origin_session_id=origin_session_id,
	)
	await invalidate_project_payload_caches(set(data.project_ids))
	return calendar


async def get_calendar(
	calendar_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Calendar:
	"""get a calendar by id."""
	return await get_accessible_calendar(calendar_id, session, principal)


async def update_calendar(
	calendar_id: TypeID,
	data: CalendarUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Calendar:
	"""update a calendar."""
	calendar = await get_accessible_calendar(
		calendar_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	changed = data.model_fields_set
	update_data = data.model_dump(exclude_unset=True, by_alias=True)
	if "is_default" in changed and data.is_default is True:
		if calendar.owner_id != principal.user_id and not principal.is_admin:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		await clear_default_calendars(
			session,
			principal,
			except_id=calendar.id,
			owner_id=calendar.owner_id,
		)
	new_project_ids: list[TypeID] | None = update_data.pop("project_ids", None)
	changed_project_ids: set[TypeID] = set()
	if new_project_ids is not None:
		old_project_ids = {project.id for project in calendar.projects}
		calendar.projects = await load_calendar_projects(
			new_project_ids,
			session,
			principal,
		)
		changed_project_ids = old_project_ids | set(new_project_ids)
	for key, value in update_data.items():
		setattr(calendar, key, value)
	await session.flush()
	await session.refresh(calendar)
	await session.refresh(calendar, attribute_names=["projects"])
	await publish_calendar(
		session,
		calendar=calendar,
		event_type=EventType.CALENDAR_UPDATED,
		origin_session_id=origin_session_id,
		extra_data={
			"affected_project_ids": [
				str(project_id) for project_id in changed_project_ids
			]
		}
		if changed_project_ids
		else None,
	)
	await invalidate_calendar_scheduled_items(calendar.id)
	if changed_project_ids:
		await invalidate_accessible_users_for_resource(
			ResourceType.CALENDAR, calendar_id, session
		)
	await invalidate_project_payload_caches(changed_project_ids)
	return calendar


async def delete_calendar(
	calendar_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a calendar and its events."""
	calendar = await get_accessible_calendar(
		calendar_id,
		session,
		principal,
		required_level=AccessLevel.ADMIN,
	)
	if calendar.is_default:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="default calendar cannot be deleted",
		)
	project_ids = {project.id for project in calendar.projects}
	result = await session.execute(
		select(CalendarEvent).where(
			CalendarEvent.calendar_id == calendar.id,
		)
	)
	calendar_events = list(result.scalars().all())
	for calendar_event in calendar_events:
		await publish_calendar_event(
			session,
			calendar_event=calendar_event,
			event_type=EventType.CALENDAR_EVENT_DELETED,
			origin_session_id=origin_session_id,
		)
		await cancel_calendar_event_notifications(calendar_event.id)
		await remove_vectorized_resource(
			spec=CALENDAR_EVENT_SPEC,
			resource_id=str(calendar_event.id),
			session=session,
		)
	await publish_calendar(
		session,
		calendar=calendar,
		event_type=EventType.CALENDAR_DELETED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_scheduled_items(calendar.id)
	await invalidate_accessible_users_for_resource(
		ResourceType.CALENDAR, calendar_id, session
	)
	await invalidate_project_payload_caches(project_ids)
	await session.delete(calendar)
	await session.flush()
