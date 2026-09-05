"""Reminder scheduled TaskIQ jobs."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from api.database import async_session_local
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.reminder import Reminder, ReminderStatus
from api.settings import settings
from api.taskiq import broker
from api.v1.service.notifications import deliver_notification
from api.v1.service.reminders.notifications import (
	_load_completed_occurrences,
	_load_reminder_delivery_keys,
	_reminder_delivery_key,
	_reminder_notification_icon_url,
	_reminder_notification_occurrences,
	_reminder_occurrence_due_at,
	dispatch_reminder_notification,
	schedule_reminder_notifications,
)
from nokodo_ai.utils.typeid import new_typeid


_registered_shared_tasks = (dispatch_reminder_notification,)


@broker.task(
	task_name="reminders.dispatch_due_notifications",
)
async def dispatch_due_reminder_notifications() -> int:
	"""send notifications for pending reminders whose remind_at has arrived."""
	now = datetime.now(tz=UTC)
	notifications: list[Notification] = []
	async with async_session_local() as session:
		missed_grace = timedelta(days=settings.notifications.missed_grace_days)
		result = await session.execute(
			select(Reminder)
			.where(Reminder.status == ReminderStatus.PENDING)
			.where(Reminder.remind_at.is_not(None))
			.where(Reminder.remind_at <= now)
			.where(
				or_(
					Reminder.recurrence.is_(None),
					Reminder.recurrence_until.is_(None),
					Reminder.recurrence_until >= now - missed_grace,
				)
			)
			.where(
				or_(
					Reminder.recurrence.is_not(None),
					Reminder.remind_at >= now - missed_grace,
				)
			)
			.with_for_update(of=Reminder, skip_locked=True)
			.limit(100)
		)
		reminders = list(result.scalars().all())
		reminder_ids = [reminder.id for reminder in reminders]
		delivery_keys = await _load_reminder_delivery_keys(session, reminder_ids)
		completed_occurrences = await _load_completed_occurrences(
			session,
			reminder_ids,
		)
		for reminder in reminders:
			for occurrence_remind_at in _reminder_notification_occurrences(
				reminder,
				completed_occurrences,
				now,
			):
				delivery_key = _reminder_delivery_key(
					reminder.owner_id,
					reminder.id,
					occurrence_remind_at,
				)
				if delivery_key in delivery_keys:
					continue
				occurrence_due_at = _reminder_occurrence_due_at(
					reminder,
					occurrence_remind_at,
				)
				title = f"reminder: {reminder.title}"
				body = reminder.description or reminder.title
				icon_url = _reminder_notification_icon_url()
				event = Event(
					id=new_typeid("event"),
					scope=EventScope.USER,
					scope_id=reminder.owner_id,
					type=EventType.NOTIFICATION_REMINDER_ALERT,
					data={
						"title": title,
						"body": body,
						"icon_url": icon_url,
						"reminder_id": str(reminder.id),
						"original_occurrence_at": occurrence_remind_at.isoformat(),
						"due_at": occurrence_due_at.isoformat()
						if occurrence_due_at
						else None,
						"remind_at": occurrence_remind_at.isoformat(),
					},
					user_id=reminder.owner_id,
					reminder_id=reminder.id,
				)
				session.add(event)
				notification = Notification(
					user_id=reminder.owner_id,
					event_id=event.id,
					title=title,
					body=body,
					icon_url=icon_url,
					delivery_key=delivery_key,
					notify_at=occurrence_remind_at,
				)
				session.add(notification)
				notifications.append(notification)
				delivery_keys.add(delivery_key)
		await session.commit()
		for notification in notifications:
			await session.refresh(notification, attribute_names=["event"])
			await deliver_notification(notification)
		for reminder_id in reminder_ids:
			await schedule_reminder_notifications(reminder_id, session=session)
	return len(notifications)
