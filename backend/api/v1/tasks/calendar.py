"""calendar scheduled TaskIQ jobs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.models.calendar import Calendar, CalendarEvent, CalendarEventOverride
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.permissions import ResourceType
from api.settings import settings
from api.taskiq import broker, redis_schedule_source
from api.v1.service.authorization import list_accessible_user_ids
from api.v1.service.notifications import (
	deliver_notification,
	shortcut_notification_icon_url,
)
from api.v1.service.scheduling.recurrence import expand_occurrence_starts
from nokodo_ai.types import JSONValue
from nokodo_ai.utils.typeid import TypeID, new_typeid


type CalendarDeliveryKey = str


def _calendar_notification_icon_url() -> str | None:
	return shortcut_notification_icon_url(
		settings.branding.pwa_assets.shortcut_calendar,
		"calendar.png",
	)


def _calendar_schedule_id(calendar_event_id: TypeID) -> str:
	return f"notifications:calendar-event:{calendar_event_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _calendar_delivery_key(
	user_id: TypeID,
	calendar_event_id: TypeID,
	original_occurrence_at: datetime,
	offset_minutes: int,
) -> CalendarDeliveryKey:
	return ":".join(
		(
			"calendar",
			str(user_id),
			str(calendar_event_id),
			original_occurrence_at.isoformat(),
			str(offset_minutes),
		)
	)


async def _load_calendar_delivery_keys(
	session: AsyncSession,
	event_ids: list[TypeID],
) -> set[CalendarDeliveryKey]:
	if not event_ids:
		return set()
	result = await session.execute(
		select(Notification.delivery_key)
		.join(Event, Notification.event_id == Event.id)
		.where(
			Event.calendar_event_id.in_(event_ids),
			Notification.delivery_key.is_not(None),
		)
	)
	return {key for key in result.scalars().all() if key is not None}


async def _load_event_overrides(
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


def _calendar_event_occurrence_starts(
	calendar_event: CalendarEvent,
	overrides: dict[tuple[TypeID, datetime], CalendarEventOverride],
	now: datetime,
) -> list[datetime]:
	if not calendar_event.notification_offsets:
		return []
	max_offset = max(calendar_event.notification_offsets)
	missed_grace = timedelta(days=settings.notifications.missed_grace_days)
	window_start = now - missed_grace
	window_end = now + timedelta(minutes=max_offset)
	if (
		calendar_event.recurrence_until is not None
		and calendar_event.recurrence_until < window_end
	):
		window_end = calendar_event.recurrence_until
	if window_end < window_start:
		return []
	occurrences = set(
		expand_occurrence_starts(
			calendar_event.start_at,
			calendar_event.recurrence,
			window_start,
			window_end,
		)
	)
	for (event_id, original_occurrence_at), override in overrides.items():
		if event_id != calendar_event.id:
			continue
		effective_start_at = override.new_start_at or original_occurrence_at
		if window_start <= effective_start_at <= window_end:
			occurrences.add(original_occurrence_at)
	return sorted(occurrences)


def _future_calendar_event_occurrence_starts(
	calendar_event: CalendarEvent,
	overrides: dict[tuple[TypeID, datetime], CalendarEventOverride],
	now: datetime,
) -> list[datetime]:
	if not calendar_event.notification_offsets:
		return []
	max_offset = max(calendar_event.notification_offsets)
	lookahead = timedelta(days=settings.notifications.lookahead_days)
	window_start = now + timedelta(microseconds=1)
	window_end = now + lookahead + timedelta(minutes=max_offset)
	if (
		calendar_event.recurrence_until is not None
		and calendar_event.recurrence_until < window_end
	):
		window_end = calendar_event.recurrence_until
	if window_end < window_start:
		return []
	occurrences = set(
		expand_occurrence_starts(
			calendar_event.start_at,
			calendar_event.recurrence,
			window_start,
			window_end,
		)
	)
	for (event_id, original_occurrence_at), override in overrides.items():
		if event_id != calendar_event.id:
			continue
		effective_start_at = override.new_start_at or original_occurrence_at
		if window_start <= effective_start_at <= window_end:
			occurrences.add(original_occurrence_at)
	return sorted(occurrences)


def _calendar_effective_start_at(
	original_occurrence_at: datetime,
	override: CalendarEventOverride | None,
) -> datetime:
	if override and override.new_start_at:
		return override.new_start_at
	return original_occurrence_at


def _has_pending_calendar_delivery(
	user_ids: list[TypeID],
	delivery_keys: set[CalendarDeliveryKey],
	calendar_event_id: TypeID,
	original_occurrence_at: datetime,
	offset: int,
) -> bool:
	return any(
		_calendar_delivery_key(
			user_id,
			calendar_event_id,
			original_occurrence_at,
			offset,
		)
		not in delivery_keys
		for user_id in user_ids
	)


async def _next_calendar_event_notification_at(
	calendar_event: CalendarEvent,
	session: AsyncSession,
	now: datetime,
) -> datetime | None:
	if not calendar_event.notification_offsets:
		return None
	delivery_keys = await _load_calendar_delivery_keys(session, [calendar_event.id])
	overrides = await _load_event_overrides(session, [calendar_event.id])
	user_ids = await list_accessible_user_ids(
		ResourceType.CALENDAR,
		calendar_event.calendar_id,
		session,
	)
	if not user_ids:
		return None
	missed_grace = timedelta(days=settings.notifications.missed_grace_days)
	for original_occurrence_at in _calendar_event_occurrence_starts(
		calendar_event,
		overrides,
		now,
	):
		override = overrides.get((calendar_event.id, original_occurrence_at))
		if override and override.cancelled_at:
			continue
		effective_start_at = _calendar_effective_start_at(
			original_occurrence_at,
			override,
		)
		for offset in calendar_event.notification_offsets:
			notify_at = effective_start_at - timedelta(minutes=offset)
			if notify_at > now or notify_at < now - missed_grace:
				continue
			if _has_pending_calendar_delivery(
				user_ids,
				delivery_keys,
				calendar_event.id,
				original_occurrence_at,
				offset,
			):
				return now
	future_notify_at: datetime | None = None
	for original_occurrence_at in _future_calendar_event_occurrence_starts(
		calendar_event,
		overrides,
		now,
	):
		override = overrides.get((calendar_event.id, original_occurrence_at))
		if override and override.cancelled_at:
			continue
		effective_start_at = _calendar_effective_start_at(
			original_occurrence_at,
			override,
		)
		for offset in calendar_event.notification_offsets:
			notify_at = effective_start_at - timedelta(minutes=offset)
			if notify_at <= now:
				continue
			if not _has_pending_calendar_delivery(
				user_ids,
				delivery_keys,
				calendar_event.id,
				original_occurrence_at,
				offset,
			):
				continue
			if future_notify_at is None or notify_at < future_notify_at:
				future_notify_at = notify_at
	return future_notify_at


async def schedule_calendar_event_notifications(
	calendar_event_id: TypeID,
	session: AsyncSession | None = None,
) -> None:
	"""schedule the next notification task for a calendar event resource."""
	if boot_settings.TESTING:
		return
	schedule_id = _calendar_schedule_id(calendar_event_id)
	await redis_schedule_source.delete_schedule(schedule_id)

	async def schedule_with(active_session: AsyncSession) -> None:
		calendar_event = await active_session.get(CalendarEvent, calendar_event_id)
		if calendar_event is None:
			return
		next_notify_at = await _next_calendar_event_notification_at(
			calendar_event,
			active_session,
			datetime.now(tz=UTC),
		)
		if next_notify_at is None:
			return
		await (
			dispatch_calendar_event_notification.kicker()
			.with_schedule_id(
				schedule_id,
			)
			.schedule_by_time(
				redis_schedule_source,
				_ceil_to_minute(next_notify_at),
				calendar_event_id,
			)
		)

	if session is not None:
		await schedule_with(session)
		return
	async with async_session_local() as new_session:
		await schedule_with(new_session)


async def cancel_calendar_event_notifications(calendar_event_id: TypeID) -> None:
	"""cancel the pending notification task for a calendar event resource."""
	if boot_settings.TESTING:
		return
	await redis_schedule_source.delete_schedule(
		_calendar_schedule_id(calendar_event_id),
	)


async def reconcile_calendar_event_notification_schedules() -> int:
	"""rebuild calendar notification schedules from durable event state."""
	if boot_settings.TESTING:
		return 0
	now = datetime.now(tz=UTC)
	missed_grace = timedelta(days=settings.notifications.missed_grace_days)
	lookahead = timedelta(days=settings.notifications.lookahead_days)
	async with async_session_local() as session:
		result = await session.execute(
			select(CalendarEvent.id)
			.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
			.where(func.cardinality(CalendarEvent.notification_offsets) > 0)
			.where(
				or_(
					CalendarEvent.start_at >= now - missed_grace,
					CalendarEvent.recurrence.is_not(None),
				)
			)
			.where(CalendarEvent.start_at <= now + lookahead)
			.where(
				or_(
					CalendarEvent.recurrence_until.is_(None),
					CalendarEvent.recurrence_until >= now - missed_grace,
				)
			)
		)
		calendar_event_ids = [
			TypeID(str(calendar_event_id)) for calendar_event_id in result.scalars()
		]
		for calendar_event_id in calendar_event_ids:
			await schedule_calendar_event_notifications(
				calendar_event_id,
				session=session,
			)
		return len(calendar_event_ids)


def _patch_text(
	patch: Mapping[str, JSONValue],
	key: str,
	fallback: str,
) -> str:
	value = patch.get(key)
	return value if isinstance(value, str) else fallback


def _patch_optional_text(
	patch: Mapping[str, JSONValue],
	key: str,
	fallback: str | None,
) -> str | None:
	if key not in patch:
		return fallback
	value = patch.get(key)
	return value if isinstance(value, str) or value is None else fallback


@broker.task(
	task_name="calendar.dispatch_due_notifications",
)
async def dispatch_due_calendar_notifications() -> int:
	"""send notifications for calendar event offsets that have arrived."""
	now = datetime.now(tz=UTC)
	notifications: list[Notification] = []
	async with async_session_local() as session:
		missed_grace = timedelta(days=settings.notifications.missed_grace_days)
		lookahead = timedelta(days=settings.notifications.lookahead_days)
		result = await session.execute(
			select(CalendarEvent)
			.join(Calendar, CalendarEvent.calendar_id == Calendar.id)
			.where(func.cardinality(CalendarEvent.notification_offsets) > 0)
			.where(
				or_(
					CalendarEvent.start_at >= now - missed_grace,
					CalendarEvent.recurrence.is_not(None),
				)
			)
			.where(CalendarEvent.start_at <= now + lookahead)
			.where(
				or_(
					CalendarEvent.recurrence_until.is_(None),
					CalendarEvent.recurrence_until >= now - missed_grace,
				)
			)
			.order_by(CalendarEvent.start_at.asc())
			.with_for_update(of=CalendarEvent, skip_locked=True)
			.limit(500)
		)
		calendar_events = list(result.scalars().all())
		event_ids = [calendar_event.id for calendar_event in calendar_events]
		delivery_keys = await _load_calendar_delivery_keys(session, event_ids)
		overrides = await _load_event_overrides(
			session,
			event_ids,
		)
		for calendar_event in calendar_events:
			user_ids = await list_accessible_user_ids(
				ResourceType.CALENDAR,
				calendar_event.calendar_id,
				session,
			)
			occurrence_starts = _calendar_event_occurrence_starts(
				calendar_event,
				overrides,
				now,
			)
			for original_occurrence_at in occurrence_starts:
				override = overrides.get((calendar_event.id, original_occurrence_at))
				if override and override.cancelled_at:
					continue
				effective_start_at = (
					override.new_start_at
					if override and override.new_start_at
					else original_occurrence_at
				)
				patch = override.payload_patch if override else {}
				for offset in calendar_event.notification_offsets:
					notify_at = effective_start_at - timedelta(minutes=offset)
					if notify_at > now or notify_at < now - missed_grace:
						continue
					for user_id in user_ids:
						delivery_key = _calendar_delivery_key(
							user_id,
							calendar_event.id,
							original_occurrence_at,
							offset,
						)
						if delivery_key in delivery_keys:
							continue
						title = _patch_text(patch, "title", calendar_event.title)
						description = _patch_optional_text(
							patch,
							"description",
							calendar_event.description,
						)
						notification_title = f"calendar: {title}"
						notification_body = description or title
						icon_url = _calendar_notification_icon_url()
						event = Event(
							id=new_typeid("event"),
							scope=EventScope.USER,
							scope_id=user_id,
							type=EventType.NOTIFICATION_CALENDAR_EVENT_ALERT,
							data={
								"title": notification_title,
								"body": notification_body,
								"icon_url": icon_url,
								"calendar_event_id": str(calendar_event.id),
								"calendar_id": str(calendar_event.calendar_id),
								"original_occurrence_at": (
									original_occurrence_at.isoformat()
								),
								"start_at": effective_start_at.isoformat(),
								"notification_offset": offset,
								"notify_at": notify_at.isoformat(),
							},
							user_id=user_id,
							calendar_event_id=calendar_event.id,
						)
						session.add(event)
						await session.flush()
						notification = Notification(
							user_id=user_id,
							event_id=event.id,
							title=notification_title,
							body=notification_body,
							icon_url=icon_url,
							delivery_key=delivery_key,
							notify_at=notify_at,
						)
						session.add(notification)
						notifications.append(notification)
						delivery_keys.add(delivery_key)
		await session.commit()
		for notification in notifications:
			await session.refresh(notification, attribute_names=["event"])
			await deliver_notification(notification)
		for event_id in event_ids:
			await schedule_calendar_event_notifications(event_id, session=session)
	return len(notifications)


@broker.task(task_name="calendar.dispatch_event_notification")
async def dispatch_calendar_event_notification(calendar_event_id: TypeID) -> int:
	"""send due notifications for one event and schedule its next alert."""
	now = datetime.now(tz=UTC)
	notifications: list[Notification] = []
	async with async_session_local() as session:
		result = await session.execute(
			select(CalendarEvent)
			.where(CalendarEvent.id == calendar_event_id)
			.with_for_update(of=CalendarEvent, skip_locked=True)
		)
		calendar_event = result.scalar_one_or_none()
		if calendar_event is None:
			await cancel_calendar_event_notifications(calendar_event_id)
			return 0
		user_ids = await list_accessible_user_ids(
			ResourceType.CALENDAR,
			calendar_event.calendar_id,
			session,
		)
		delivery_keys = await _load_calendar_delivery_keys(
			session,
			[calendar_event.id],
		)
		overrides = await _load_event_overrides(
			session,
			[calendar_event.id],
		)
		missed_grace = timedelta(days=settings.notifications.missed_grace_days)
		occurrence_starts = _calendar_event_occurrence_starts(
			calendar_event,
			overrides,
			now,
		)
		for original_occurrence_at in occurrence_starts:
			override = overrides.get((calendar_event.id, original_occurrence_at))
			if override and override.cancelled_at:
				continue
			effective_start_at = _calendar_effective_start_at(
				original_occurrence_at,
				override,
			)
			patch = override.payload_patch if override else {}
			for offset in calendar_event.notification_offsets:
				notify_at = effective_start_at - timedelta(minutes=offset)
				if notify_at > now or notify_at < now - missed_grace:
					continue
				for user_id in user_ids:
					delivery_key = _calendar_delivery_key(
						user_id,
						calendar_event.id,
						original_occurrence_at,
						offset,
					)
					if delivery_key in delivery_keys:
						continue
					title = _patch_text(patch, "title", calendar_event.title)
					description = _patch_optional_text(
						patch,
						"description",
						calendar_event.description,
					)
					notification_title = f"calendar: {title}"
					notification_body = description or title
					icon_url = _calendar_notification_icon_url()
					event = Event(
						id=new_typeid("event"),
						scope=EventScope.USER,
						scope_id=user_id,
						type=EventType.NOTIFICATION_CALENDAR_EVENT_ALERT,
						data={
							"title": notification_title,
							"body": notification_body,
							"icon_url": icon_url,
							"calendar_event_id": str(calendar_event.id),
							"calendar_id": str(calendar_event.calendar_id),
							"original_occurrence_at": (
								original_occurrence_at.isoformat()
							),
							"start_at": effective_start_at.isoformat(),
							"notification_offset": offset,
							"notify_at": notify_at.isoformat(),
						},
						user_id=user_id,
						calendar_event_id=calendar_event.id,
					)
					session.add(event)
					await session.flush()
					notification = Notification(
						user_id=user_id,
						event_id=event.id,
						title=notification_title,
						body=notification_body,
						icon_url=icon_url,
						delivery_key=delivery_key,
						notify_at=notify_at,
					)
					session.add(notification)
					notifications.append(notification)
					delivery_keys.add(delivery_key)
		await session.commit()
		for notification in notifications:
			await session.refresh(notification, attribute_names=["event"])
			await deliver_notification(notification)
		await schedule_calendar_event_notifications(
			calendar_event_id,
			session=session,
		)
	return len(notifications)
