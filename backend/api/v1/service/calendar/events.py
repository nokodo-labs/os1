"""calendar event and occurrence service helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.calendar import Calendar, CalendarEvent, CalendarEventOverride
from api.models.event_types import EventType
from api.permissions import ResourceType
from api.schemas.calendar import (
	CalendarEventCreate,
	CalendarEventListFilters,
	CalendarEventUpdate,
)
from api.schemas.scheduled_item import (
	CalendarOccurrenceEdit,
	CalendarSeriesEdit,
	ScheduledItem,
)
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission, resource_access_predicate
from api.v1.service.calendar.cache import (
	get_cached_calendar_event_items,
	invalidate_calendar_event_scheduled_items,
	set_cached_calendar_event_items,
)
from api.v1.service.calendar.common import (
	CALENDAR_CREATE_PERMISSION,
	get_accessible_calendar,
	get_accessible_calendar_event,
	get_or_create_default_calendar,
	publish_calendar_event,
	validate_calendar_event_range,
)
from api.v1.service.calendar.search import CALENDAR_EVENT_SPEC
from api.v1.service.scheduling.recurrence import (
	expand_occurrence_starts,
	occurrence_exists,
	recurrence_after_split,
	recurrence_to_storage,
)
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorize import remove_vectorized_resource, vectorize_resource
from api.v1.tasks.calendar import (
	cancel_calendar_event_notifications,
	schedule_calendar_event_notifications,
)
from nokodo_ai.types import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


_CALENDAR_EVENT_SORT_COLUMNS = {
	"start_at": CalendarEvent.start_at,
	"end_at": CalendarEvent.end_at,
	"title": CalendarEvent.title,
	"created_at": CalendarEvent.created_at,
	"updated_at": CalendarEvent.updated_at,
}


async def list_calendar_events(
	session: AsyncSession,
	principal: Principal,
	filters: CalendarEventListFilters | None = None,
	calendar_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 500,
	sort_by: str = "start_at",
	sort_dir: SortDir = "asc",
) -> list[CalendarEvent]:
	"""list calendar events accessible to the principal."""
	event_filters = filters or CalendarEventListFilters()
	stmt = (
		select(CalendarEvent)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			resource_access_predicate(principal, ResourceType.CALENDAR),
		)
	)
	if event_filters.start_at is not None:
		stmt = stmt.where(CalendarEvent.end_at >= event_filters.start_at)
	if event_filters.end_at is not None:
		stmt = stmt.where(CalendarEvent.start_at <= event_filters.end_at)
	if calendar_id is not None:
		await get_accessible_calendar(calendar_id, session, principal)
		stmt = stmt.where(CalendarEvent.calendar_id == calendar_id)
	if event_filters.q is not None and event_filters.q.strip():
		pattern = contains_pattern(event_filters.q.strip())
		stmt = stmt.where(
			or_(
				CalendarEvent.title.ilike(pattern, escape="\\"),
				CalendarEvent.description.ilike(pattern, escape="\\"),
			)
		)
	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns=_CALENDAR_EVENT_SORT_COLUMNS,
		tie_breaker=CalendarEvent.id,
	)
	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().all())


async def list_calendar_scheduled_items(
	session: AsyncSession,
	principal: Principal,
	start_at: datetime,
	end_at: datetime,
) -> list[ScheduledItem]:
	"""list calendar-owned scheduled item occurrences."""
	event_rows = await _load_calendar_scheduled_rows(
		session,
		principal,
		start_at,
		end_at,
	)
	overrides = await _load_calendar_event_overrides(
		session,
		[event.id for event, _calendar in event_rows],
	)
	items: list[ScheduledItem] = []
	for event, calendar in event_rows:
		cached_items = await get_cached_calendar_event_items(
			event.id,
			start_at,
			end_at,
		)
		if cached_items is not None:
			items.extend(cached_items)
			continue
		event_items = _expand_calendar_scheduled_item(
			event,
			calendar,
			overrides,
			start_at,
			end_at,
		)
		await set_cached_calendar_event_items(
			event.id,
			calendar.id,
			start_at,
			end_at,
			event_items,
		)
		items.extend(event_items)
	return items


async def _load_calendar_scheduled_rows(
	session: AsyncSession,
	principal: Principal,
	start_at: datetime,
	end_at: datetime,
) -> list[tuple[CalendarEvent, Calendar]]:
	stmt = (
		select(CalendarEvent, Calendar)
		.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
		.where(
			CalendarEvent.start_at <= end_at,
			or_(
				CalendarEvent.end_at >= start_at,
				CalendarEvent.recurrence.is_not(None),
			),
			or_(
				CalendarEvent.recurrence_until.is_(None),
				CalendarEvent.recurrence_until >= start_at,
			),
			resource_access_predicate(
				principal,
				ResourceType.CALENDAR,
				required_level=AccessLevel.READER,
			),
		)
	)
	result = await session.execute(stmt)
	return [(row[0], row[1]) for row in result.all()]


async def _load_calendar_event_overrides(
	session: AsyncSession,
	event_ids: list[TypeID],
) -> dict[tuple[TypeID, datetime], CalendarEventOverride]:
	if not event_ids:
		return {}
	result = await session.execute(
		select(CalendarEventOverride).where(
			CalendarEventOverride.event_id.in_(event_ids),
		)
	)
	return {
		(override.event_id, override.original_occurrence_at): override
		for override in result.scalars().all()
	}


def _expand_calendar_scheduled_item(
	event: CalendarEvent,
	calendar: Calendar,
	overrides: dict[tuple[TypeID, datetime], CalendarEventOverride],
	start_at: datetime,
	end_at: datetime,
) -> list[ScheduledItem]:
	duration = event.end_at - event.start_at
	expansion_end = _bounded_window_end(end_at, event.recurrence_until)
	if expansion_end < start_at:
		return []
	occurrences = expand_occurrence_starts(
		event.start_at,
		event.recurrence,
		start_at,
		expansion_end,
		duration=duration,
	)
	items: list[ScheduledItem] = []
	for original_start in occurrences:
		override = overrides.get((event.id, original_start))
		patch = override.payload_patch if override else {}
		effective_start = (
			override.new_start_at
			if override and override.new_start_at
			else original_start
		)
		effective_end = (
			override.new_end_at
			if override and override.new_end_at
			else effective_start + duration
		)
		if not _overlaps(effective_start, effective_end, start_at, end_at):
			continue
		is_cancelled = bool(override and override.cancelled_at)
		items.append(
			ScheduledItem(
				kind="event",
				id=_calendar_occurrence_id(event.id, original_start),
				parent_id=event.id,
				container_id=calendar.id,
				calendar_id=calendar.id,
				original_occurrence_at=original_start,
				effective_start_at=effective_start,
				effective_end_at=effective_end,
				all_day=event.all_day,
				title=_patch_text(patch, "title", event.title),
				description=_patch_optional_text(
					patch,
					"description",
					event.description,
				),
				color=calendar.color,
				status="cancelled" if is_cancelled else "scheduled",
				readonly=is_cancelled,
			)
		)
	return items


async def create_calendar_event(
	data: CalendarEventCreate,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> CalendarEvent:
	"""create a calendar event."""
	if calendar_id is None:
		require_permission(principal, CALENDAR_CREATE_PERMISSION)
	calendar = (
		await get_accessible_calendar(
			calendar_id,
			session,
			principal,
			required_level=AccessLevel.EDITOR,
		)
		if calendar_id is not None
		else await get_or_create_default_calendar(session, principal)
	)
	create_data = data.model_dump(
		exclude_unset=True,
		by_alias=True,
		exclude={"recurrence"},
	)
	create_data["recurrence"] = recurrence_to_storage(data.recurrence)
	calendar_event = CalendarEvent(
		owner_id=calendar.owner_id,
		calendar_id=calendar.id,
		**create_data,
	)
	session.add(calendar_event)
	await session.flush()
	await session.refresh(calendar_event)
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_CREATED,
		origin_session_id=origin_session_id,
	)
	await vectorize_resource(
		spec=CALENDAR_EVENT_SPEC,
		resource=calendar_event,
		session=session,
	)
	await schedule_calendar_event_notifications(calendar_event.id, session=session)
	return calendar_event


async def get_calendar_event(
	event_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
) -> CalendarEvent:
	"""get a calendar event by id."""
	return await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		calendar_id=calendar_id,
	)


async def update_calendar_event(
	event_id: TypeID,
	data: CalendarEventUpdate,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> CalendarEvent:
	"""update a calendar event."""
	calendar_event = await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		calendar_id=calendar_id,
	)
	changed = data.model_fields_set
	update_data = data.model_dump(exclude_unset=True, by_alias=True)
	if "recurrence" in changed:
		update_data["recurrence"] = recurrence_to_storage(data.recurrence)
	start_at = data.start_at if data.start_at is not None else calendar_event.start_at
	end_at = data.end_at if data.end_at is not None else calendar_event.end_at
	validate_calendar_event_range(start_at, end_at)
	if "title" in changed and data.title is not None:
		calendar_event.title = data.title
	if "description" in changed:
		calendar_event.description = data.description
	if "start_at" in changed and data.start_at is not None:
		calendar_event.start_at = data.start_at
	if "end_at" in changed and data.end_at is not None:
		calendar_event.end_at = data.end_at
	if "all_day" in changed and data.all_day is not None:
		calendar_event.all_day = data.all_day
	if "timezone" in changed:
		calendar_event.timezone = data.timezone
	if "recurrence" in changed:
		calendar_event.recurrence = update_data["recurrence"]
	if "notification_offsets" in changed and data.notification_offsets is not None:
		calendar_event.notification_offsets = data.notification_offsets
	if "location" in changed:
		calendar_event.location = data.location
		if data.location:
			calendar_event.virtual_url = None
	if "virtual_url" in changed:
		calendar_event.virtual_url = data.virtual_url
		if data.virtual_url:
			calendar_event.location = None
	if "labels" in changed and data.labels is not None:
		calendar_event.labels = data.labels
	if "metadata" in changed and data.metadata is not None:
		calendar_event.metadata_ = data.metadata
	await session.flush()
	await session.refresh(calendar_event)
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_UPDATED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_event_scheduled_items(calendar_event.id)
	await schedule_calendar_event_notifications(calendar_event.id, session=session)
	if await CALENDAR_EVENT_SPEC.should_revectorize(calendar_event, data, session):
		await vectorize_resource(
			spec=CALENDAR_EVENT_SPEC,
			resource=calendar_event,
			session=session,
		)
	return calendar_event


async def edit_calendar_event_occurrence(
	event_id: TypeID,
	data: CalendarOccurrenceEdit,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> ScheduledItem:
	"""edit a single calendar event occurrence."""
	calendar_event = await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		calendar_id=calendar_id,
	)
	_validate_event_occurrence(calendar_event, data.original_occurrence_at)
	override = await session.get(
		CalendarEventOverride,
		(calendar_event.id, data.original_occurrence_at),
	)
	if override is None:
		override = CalendarEventOverride(
			event_id=calendar_event.id,
			original_occurrence_at=data.original_occurrence_at,
			cancelled_at=None,
			new_start_at=None,
			new_end_at=None,
			payload_patch={},
		)
		session.add(override)
	else:
		override.cancelled_at = None
	override.new_start_at = data.new_start_at
	override.new_end_at = data.new_end_at
	override.payload_patch = _calendar_occurrence_payload_patch(data)
	await session.flush()
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_UPDATED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_event_scheduled_items(calendar_event.id)
	await schedule_calendar_event_notifications(calendar_event.id, session=session)
	return _calendar_occurrence_item(calendar_event, override)


async def cancel_calendar_event_occurrence(
	event_id: TypeID,
	original_occurrence_at: datetime,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> None:
	"""cancel a single calendar event occurrence."""
	calendar_event = await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		calendar_id=calendar_id,
	)
	_validate_event_occurrence(calendar_event, original_occurrence_at)
	now = datetime.now(UTC)
	override = await session.get(
		CalendarEventOverride,
		(calendar_event.id, original_occurrence_at),
	)
	if override is None:
		override = CalendarEventOverride(
			event_id=calendar_event.id,
			original_occurrence_at=original_occurrence_at,
			cancelled_at=now,
			new_start_at=None,
			new_end_at=None,
			payload_patch={},
		)
		session.add(override)
	else:
		override.cancelled_at = now
	await session.flush()
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_UPDATED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_event_scheduled_items(calendar_event.id)
	await schedule_calendar_event_notifications(calendar_event.id, session=session)


async def edit_calendar_event_series(
	event_id: TypeID,
	data: CalendarSeriesEdit,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> CalendarEvent:
	"""split a recurring event and edit this/following occurrences."""
	calendar_event = await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		calendar_id=calendar_id,
	)
	_validate_event_series_split(calendar_event, data.original_occurrence_at)
	new_event = _build_calendar_event_split(calendar_event, data)
	calendar_event.recurrence_until = _split_cutoff(data.original_occurrence_at)
	session.add(new_event)
	await session.flush()
	await _move_calendar_event_overrides_after_split(
		session,
		from_event=calendar_event,
		to_event=new_event,
		split_at=data.original_occurrence_at,
		keep_future=bool(new_event.recurrence),
	)
	await session.refresh(calendar_event)
	await session.refresh(new_event)
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_UPDATED,
		origin_session_id=origin_session_id,
	)
	await publish_calendar_event(
		session,
		calendar_event=new_event,
		event_type=EventType.CALENDAR_EVENT_CREATED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_event_scheduled_items(calendar_event.id)
	await vectorize_resource(
		spec=CALENDAR_EVENT_SPEC,
		resource=calendar_event,
		session=session,
	)
	await vectorize_resource(
		spec=CALENDAR_EVENT_SPEC,
		resource=new_event,
		session=session,
	)
	await schedule_calendar_event_notifications(calendar_event.id, session=session)
	await schedule_calendar_event_notifications(new_event.id, session=session)
	return new_event


def _validate_event_occurrence(
	calendar_event: CalendarEvent,
	original_occurrence_at: datetime,
) -> None:
	if _after_recurrence_until(calendar_event.recurrence_until, original_occurrence_at):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="occurrence does not belong to event recurrence",
		)
	if not occurrence_exists(
		calendar_event.start_at,
		calendar_event.recurrence,
		original_occurrence_at,
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="occurrence does not belong to event recurrence",
		)


def _validate_event_series_split(
	calendar_event: CalendarEvent,
	original_occurrence_at: datetime,
) -> None:
	if calendar_event.recurrence is None:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
			detail="event is not recurring",
		)
	_validate_event_occurrence(calendar_event, original_occurrence_at)


def _after_recurrence_until(
	recurrence_until: datetime | None,
	original_occurrence_at: datetime,
) -> bool:
	return recurrence_until is not None and original_occurrence_at > recurrence_until


def _split_cutoff(original_occurrence_at: datetime) -> datetime:
	return original_occurrence_at - timedelta(microseconds=1)


def _build_calendar_event_split(
	calendar_event: CalendarEvent,
	data: CalendarSeriesEdit,
) -> CalendarEvent:
	changed = data.model_fields_set
	duration = calendar_event.end_at - calendar_event.start_at
	new_start_at = data.new_start_at or data.original_occurrence_at
	new_end_at = data.new_end_at or new_start_at + duration
	validate_calendar_event_range(new_start_at, new_end_at)
	return CalendarEvent(
		owner_id=calendar_event.owner_id,
		calendar_id=calendar_event.calendar_id,
		title=data.title if data.title is not None else calendar_event.title,
		description=data.description
		if "description" in changed
		else calendar_event.description,
		start_at=new_start_at,
		end_at=new_end_at,
		all_day=data.all_day if data.all_day is not None else calendar_event.all_day,
		timezone=data.timezone if "timezone" in changed else calendar_event.timezone,
		recurrence=recurrence_to_storage(data.recurrence)
		if "recurrence" in changed
		else recurrence_to_storage(
			recurrence_after_split(
				calendar_event.start_at,
				calendar_event.recurrence,
				data.original_occurrence_at,
			)
		),
		recurrence_until=None,
		series_origin_id=calendar_event.series_origin_id or calendar_event.id,
		notification_offsets=data.notification_offsets
		if data.notification_offsets is not None
		else list(calendar_event.notification_offsets or []),
		location=data.location if "location" in changed else calendar_event.location,
		virtual_url=data.virtual_url
		if "virtual_url" in changed
		else calendar_event.virtual_url,
		labels=data.labels
		if data.labels is not None
		else list(calendar_event.labels or []),
		metadata_=dict(calendar_event.metadata_ or {}),
	)


async def _move_calendar_event_overrides_after_split(
	session: AsyncSession,
	from_event: CalendarEvent,
	to_event: CalendarEvent,
	split_at: datetime,
	keep_future: bool,
) -> None:
	result = await session.execute(
		select(CalendarEventOverride).where(
			CalendarEventOverride.event_id == from_event.id,
			CalendarEventOverride.original_occurrence_at >= split_at,
		)
	)
	for override in result.scalars().all():
		if keep_future and override.original_occurrence_at > split_at:
			session.add(
				CalendarEventOverride(
					event_id=to_event.id,
					original_occurrence_at=override.original_occurrence_at,
					cancelled_at=override.cancelled_at,
					new_start_at=override.new_start_at,
					new_end_at=override.new_end_at,
					payload_patch=dict(override.payload_patch or {}),
				)
			)
		await session.delete(override)


def _calendar_occurrence_payload_patch(data: CalendarOccurrenceEdit) -> JSONObject:
	patch: JSONObject = {}
	if data.title is not None:
		patch["title"] = data.title
	if data.description is not None:
		patch["description"] = data.description
	if data.location is not None:
		patch["location"] = data.location
	if data.virtual_url is not None:
		patch["virtual_url"] = data.virtual_url
	return patch


def _calendar_occurrence_item(
	calendar_event: CalendarEvent,
	override: CalendarEventOverride,
) -> ScheduledItem:
	duration = calendar_event.end_at - calendar_event.start_at
	effective_start = override.new_start_at or override.original_occurrence_at
	effective_end = override.new_end_at or effective_start + duration
	return ScheduledItem(
		kind="event",
		id=_calendar_occurrence_id(
			calendar_event.id,
			override.original_occurrence_at,
		),
		parent_id=calendar_event.id,
		container_id=calendar_event.calendar_id,
		calendar_id=calendar_event.calendar_id,
		original_occurrence_at=override.original_occurrence_at,
		effective_start_at=effective_start,
		effective_end_at=effective_end,
		all_day=calendar_event.all_day,
		title=_patch_text(override.payload_patch, "title", calendar_event.title),
		description=_patch_optional_text(
			override.payload_patch,
			"description",
			calendar_event.description,
		),
		color=None,
		status="cancelled" if override.cancelled_at else "scheduled",
		readonly=bool(override.cancelled_at),
	)


def _calendar_occurrence_id(event_id: TypeID, original_start: datetime) -> str:
	return f"event:{event_id}:{original_start.isoformat()}"


def _bounded_window_end(
	window_end: datetime, recurrence_until: datetime | None
) -> datetime:
	if recurrence_until is None or recurrence_until > window_end:
		return window_end
	return recurrence_until


def _overlaps(
	start_at: datetime,
	end_at: datetime,
	window_start: datetime,
	window_end: datetime,
) -> bool:
	return start_at <= window_end and end_at >= window_start


def _patch_text(patch: JSONObject, key: str, fallback: str) -> str:
	value = patch.get(key)
	return value if isinstance(value, str) else fallback


def _patch_optional_text(
	patch: JSONObject,
	key: str,
	fallback: str | None,
) -> str | None:
	value = patch.get(key)
	return value if isinstance(value, str) or value is None else fallback


async def delete_calendar_event(
	event_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	calendar_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> None:
	"""delete a calendar event."""
	calendar_event = await get_accessible_calendar_event(
		event_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
		calendar_id=calendar_id,
	)
	await publish_calendar_event(
		session,
		calendar_event=calendar_event,
		event_type=EventType.CALENDAR_EVENT_DELETED,
		origin_session_id=origin_session_id,
	)
	await invalidate_calendar_event_scheduled_items(calendar_event.id)
	await cancel_calendar_event_notifications(calendar_event.id)
	await remove_vectorized_resource(
		spec=CALENDAR_EVENT_SPEC,
		resource_id=str(calendar_event.id),
		session=session,
	)
	await session.delete(calendar_event)
	await session.flush()
