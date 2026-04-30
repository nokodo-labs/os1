"""Reminder scheduled TaskIQ jobs."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from api.database import async_session_local
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.reminder import Reminder, ReminderStatus
from api.taskiq import broker
from api.v1.service.events import event_connections
from nokodo_ai.utils.typeid import new_typeid


@broker.task(
	task_name="reminders.dispatch_due_notifications",
	schedule=[{"cron": "* * * * *"}],
)
async def dispatch_due_reminder_notifications() -> int:
	"""send notifications for pending reminders whose remind_at has arrived."""
	now = datetime.now(tz=UTC)
	notifications: list[Notification] = []
	async with async_session_local() as session:
		result = await session.execute(
			select(Reminder)
			.where(Reminder.status == ReminderStatus.PENDING)
			.where(Reminder.remind_at.is_not(None))
			.where(Reminder.remind_at <= now)
			.limit(100)
		)
		for reminder in result.scalars().all():
			metadata = dict(reminder.metadata_ or {})
			if isinstance(metadata.get("reminder_notification_sent_at"), str):
				continue
			event = Event(
				id=new_typeid("event"),
				scope=EventScope.USER,
				scope_id=reminder.owner_id,
				type=EventType.NOTIFICATION_CUSTOM,
				data={
					"title": f"Reminder: {reminder.title}",
					"body": reminder.description or reminder.title,
					"reminder_id": str(reminder.id),
					"due_at": reminder.due_at.isoformat() if reminder.due_at else None,
					"remind_at": reminder.remind_at.isoformat()
					if reminder.remind_at
					else None,
				},
				user_id=reminder.owner_id,
			)
			session.add(event)
			await session.flush()
			notification = Notification(user_id=reminder.owner_id, event_id=event.id)
			session.add(notification)
			notifications.append(notification)
			metadata["reminder_notification_sent_at"] = now.isoformat()
			reminder.metadata_ = metadata
		await session.commit()
		for notification in notifications:
			await session.refresh(notification, attribute_names=["event"])
			await event_connections.broadcast_event(notification.event)
	return len(notifications)
