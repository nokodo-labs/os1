"""calendar scheduled TaskIQ jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select

from api.database import async_session_local
from api.models.calendar import Calendar, CalendarEvent
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.permissions import ResourceType
from api.settings import settings
from api.taskiq import broker
from api.v1.service.authorization import list_accessible_user_ids_for_resources
from api.v1.service.calendar.notifications import (
	_calendar_delivery_key,
	_calendar_event_occurrence_starts,
	_calendar_notification_icon_url,
	_load_calendar_delivery_keys,
	_load_event_overrides,
	_patch_optional_text,
	_patch_text,
	dispatch_calendar_event_notification,
	schedule_calendar_event_notifications,
)
from api.v1.service.notifications import deliver_notification
from nokodo_ai.utils.typeid import new_typeid


_registered_shared_tasks = (dispatch_calendar_event_notification,)


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
			user_ids = await list_accessible_user_ids_for_resources(
				[(ResourceType.CALENDAR, calendar_event.calendar_id)], session
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
