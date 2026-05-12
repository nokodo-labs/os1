"""shared calendar service helpers."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.access_rule import AccessLevel
from api.models.calendar import Calendar, CalendarEvent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.project import Project
from api.permissions import ActionPermission, ResourceType
from api.schemas.calendar import Calendar as CalendarOut
from api.schemas.calendar import CalendarEvent as CalendarEventOut
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_project_access,
	resource_access_predicate,
)
from api.v1.service.projects import load_projects
from nokodo_ai.utils.typeid import TypeID


CALENDAR_CREATE_PERMISSION = ActionPermission.CALENDAR_CREATE.value


def _calendar_payload(calendar: Calendar) -> dict[str, object]:
	return CalendarOut.model_validate(calendar).model_dump(
		mode="json",
		by_alias=True,
	)


def _event_payload(calendar_event: CalendarEvent) -> dict[str, object]:
	return CalendarEventOut.model_validate(calendar_event).model_dump(
		mode="json",
		by_alias=True,
	)


def validate_calendar_event_range(start_at: datetime, end_at: datetime) -> None:
	if end_at <= start_at:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="end time must be after start time",
		)


async def publish_calendar_event(
	session: AsyncSession,
	calendar_event: CalendarEvent,
	event_type: EventType,
	origin_session_id: str | None,
) -> None:
	event = Event(
		scope=EventScope.USER,
		scope_id=calendar_event.owner_id,
		type=event_type,
		data=_event_payload(calendar_event),
		user_id=calendar_event.owner_id,
		calendar_event_id=calendar_event.id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


async def publish_calendar(
	session: AsyncSession,
	calendar: Calendar,
	event_type: EventType,
	origin_session_id: str | None,
) -> None:
	event = Event(
		scope=EventScope.USER,
		scope_id=calendar.owner_id,
		type=event_type,
		data=_calendar_payload(calendar),
		user_id=calendar.owner_id,
		calendar_id=calendar.id,
	)
	await event_service.persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)


async def clear_default_calendars(
	session: AsyncSession,
	principal: Principal,
	except_id: TypeID | None = None,
	owner_id: TypeID | None = None,
) -> None:
	target_owner_id = owner_id if owner_id is not None else principal.user_id
	stmt = select(Calendar).where(
		Calendar.owner_id == target_owner_id,
		Calendar.is_default.is_(True),
	)
	if except_id is not None:
		stmt = stmt.where(Calendar.id != except_id)
	result = await session.execute(stmt)
	for calendar in result.scalars().all():
		calendar.is_default = False


async def get_accessible_calendar(
	calendar_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
) -> Calendar:
	stmt = (
		select(Calendar)
		.options(selectinload(Calendar.projects))
		.where(
			Calendar.id == calendar_id,
			resource_access_predicate(
				principal,
				ResourceType.CALENDAR,
				required_level=required_level,
			),
		)
	)
	result = await session.execute(stmt)
	calendar = result.scalar_one_or_none()
	if calendar is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="calendar not found",
		)
	return calendar


async def load_calendar_projects(
	project_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
) -> list[Project]:
	for project_id in project_ids:
		await require_project_access(
			project_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
	return await load_projects(project_ids, session, principal)


async def get_or_create_default_calendar(
	session: AsyncSession,
	principal: Principal,
) -> Calendar:
	stmt = (
		select(Calendar)
		.where(
			Calendar.owner_id == principal.user_id,
			Calendar.is_default.is_(True),
		)
		.order_by(Calendar.created_at.asc())
	)
	result = await session.execute(stmt)
	calendar = result.scalars().first()
	if calendar is not None:
		return calendar

	calendar = Calendar(
		owner_id=principal.user_id,
		name="personal",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=True,
		timezone=None,
	)
	session.add(calendar)
	await session.flush()
	return calendar


async def get_accessible_calendar_event(
	event_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
	calendar_id: TypeID | None = None,
) -> CalendarEvent:
	stmt = (
		select(CalendarEvent)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			CalendarEvent.id == event_id,
			resource_access_predicate(
				principal,
				ResourceType.CALENDAR,
				required_level=required_level,
			),
		)
	)
	if calendar_id is not None:
		stmt = stmt.where(CalendarEvent.calendar_id == calendar_id)
	result = await session.execute(stmt)
	calendar_event = result.scalar_one_or_none()
	if calendar_event is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="calendar event not found",
		)
	return calendar_event
