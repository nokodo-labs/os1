"""Reminder scheduled TaskIQ jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.reminder import Reminder, ReminderOverride, ReminderStatus
from api.settings import settings
from api.taskiq import broker, redis_schedule_source
from api.v1.service.notifications import (
	deliver_notification,
	shortcut_notification_icon_url,
)
from api.v1.service.scheduling.recurrence import expand_occurrence_starts
from nokodo_ai.utils.typeid import TypeID, new_typeid


type ReminderDeliveryKey = str


def _reminder_notification_icon_url() -> str | None:
	return shortcut_notification_icon_url(
		settings.branding.pwa_assets.shortcut_reminders,
		"reminders.png",
	)


def _reminder_schedule_id(reminder_id: TypeID) -> str:
	return f"notifications:reminder:{reminder_id}"


def _ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _reminder_delivery_key(
	user_id: TypeID,
	reminder_id: TypeID,
	original_occurrence_at: datetime,
) -> ReminderDeliveryKey:
	return ":".join(
		(
			"reminder",
			str(user_id),
			str(reminder_id),
			original_occurrence_at.isoformat(),
		)
	)


async def _load_reminder_delivery_keys(
	session: AsyncSession,
	reminder_ids: list[TypeID],
) -> set[ReminderDeliveryKey]:
	if not reminder_ids:
		return set()
	result = await session.execute(
		select(Notification.delivery_key)
		.join(Event, Notification.event_id == Event.id)
		.where(
			Event.reminder_id.in_(reminder_ids),
			Notification.delivery_key.is_not(None),
		)
	)
	return {key for key in result.scalars().all() if key is not None}


async def _load_completed_occurrences(
	session: AsyncSession,
	reminder_ids: list[TypeID],
) -> set[tuple[TypeID, datetime]]:
	if not reminder_ids:
		return set()
	result = await session.execute(
		select(ReminderOverride).where(ReminderOverride.reminder_id.in_(reminder_ids))
	)
	return {
		(override.reminder_id, override.original_occurrence_at)
		for override in result.scalars().all()
	}


def _reminder_notification_occurrences(
	reminder: Reminder,
	completed_occurrences: set[tuple[TypeID, datetime]],
	now: datetime,
) -> list[datetime]:
	if reminder.remind_at is None:
		return []
	if reminder.recurrence is None:
		occurrences = [reminder.remind_at] if reminder.remind_at <= now else []
	else:
		missed_grace = timedelta(days=settings.notifications.missed_grace_days)
		window_start = now - missed_grace
		window_end = now
		if (
			reminder.recurrence_until is not None
			and reminder.recurrence_until < window_end
		):
			window_end = reminder.recurrence_until
		if window_end < window_start:
			return []
		occurrences = expand_occurrence_starts(
			reminder.remind_at,
			reminder.recurrence,
			window_start,
			window_end,
		)
	return [
		occurrence
		for occurrence in occurrences
		if occurrence <= now and (reminder.id, occurrence) not in completed_occurrences
	]


def _reminder_occurrence_due_at(
	reminder: Reminder,
	occurrence_remind_at: datetime,
) -> datetime | None:
	if reminder.due_at is None or reminder.remind_at is None:
		return reminder.due_at
	return occurrence_remind_at + (reminder.due_at - reminder.remind_at)


def _future_reminder_notification_occurrences(
	reminder: Reminder,
	now: datetime,
) -> list[datetime]:
	if reminder.remind_at is None:
		return []
	window_start = now + timedelta(microseconds=1)
	if reminder.recurrence is None:
		return [reminder.remind_at] if reminder.remind_at >= window_start else []
	lookahead = timedelta(days=settings.notifications.lookahead_days)
	window_end = now + lookahead
	if reminder.recurrence_until is not None and reminder.recurrence_until < window_end:
		window_end = reminder.recurrence_until
	if window_end < window_start:
		return []
	return expand_occurrence_starts(
		reminder.remind_at,
		reminder.recurrence,
		window_start,
		window_end,
	)


async def _next_reminder_notification_at(
	reminder: Reminder,
	session: AsyncSession,
	now: datetime,
) -> datetime | None:
	if reminder.status != ReminderStatus.PENDING or reminder.remind_at is None:
		return None
	delivery_keys = await _load_reminder_delivery_keys(session, [reminder.id])
	completed_occurrences = await _load_completed_occurrences(session, [reminder.id])
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
		if delivery_key not in delivery_keys:
			return now
	for occurrence_remind_at in _future_reminder_notification_occurrences(
		reminder,
		now,
	):
		if (reminder.id, occurrence_remind_at) in completed_occurrences:
			continue
		delivery_key = _reminder_delivery_key(
			reminder.owner_id,
			reminder.id,
			occurrence_remind_at,
		)
		if delivery_key not in delivery_keys:
			return occurrence_remind_at
	return None


async def schedule_reminder_notifications(
	reminder_id: TypeID,
	session: AsyncSession | None = None,
) -> None:
	"""schedule the next notification task for a reminder resource."""
	if boot_settings.TESTING:
		return
	schedule_id = _reminder_schedule_id(reminder_id)
	await redis_schedule_source.delete_schedule(schedule_id)

	async def schedule_with(active_session: AsyncSession) -> None:
		reminder = await active_session.get(Reminder, reminder_id)
		if reminder is None:
			return
		next_notify_at = await _next_reminder_notification_at(
			reminder,
			active_session,
			datetime.now(tz=UTC),
		)
		if next_notify_at is None:
			return
		await (
			dispatch_reminder_notification.kicker()
			.with_schedule_id(
				schedule_id,
			)
			.schedule_by_time(
				redis_schedule_source,
				_ceil_to_minute(next_notify_at),
				reminder_id,
			)
		)

	if session is not None:
		await schedule_with(session)
		return
	async with async_session_local() as new_session:
		await schedule_with(new_session)


async def cancel_reminder_notifications(reminder_id: TypeID) -> None:
	"""cancel the pending notification task for a reminder resource."""
	if boot_settings.TESTING:
		return
	await redis_schedule_source.delete_schedule(_reminder_schedule_id(reminder_id))


async def reconcile_reminder_notification_schedules() -> int:
	"""rebuild reminder notification schedules from durable reminder state."""
	if boot_settings.TESTING:
		return 0
	now = datetime.now(tz=UTC)
	missed_grace = timedelta(days=settings.notifications.missed_grace_days)
	async with async_session_local() as session:
		result = await session.execute(
			select(Reminder.id)
			.where(Reminder.status == ReminderStatus.PENDING)
			.where(Reminder.remind_at.is_not(None))
			.where(
				or_(
					Reminder.recurrence_until.is_(None),
					Reminder.recurrence_until >= now - missed_grace,
				)
			)
		)
		reminder_ids = [TypeID(str(reminder_id)) for reminder_id in result.scalars()]
		for reminder_id in reminder_ids:
			await schedule_reminder_notifications(reminder_id, session=session)
		return len(reminder_ids)


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
				await session.flush()
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


@broker.task(task_name="reminders.dispatch_notification")
async def dispatch_reminder_notification(reminder_id: TypeID) -> int:
	"""send due notifications for one reminder and schedule its next alert."""
	now = datetime.now(tz=UTC)
	notifications: list[Notification] = []
	async with async_session_local() as session:
		result = await session.execute(
			select(Reminder)
			.where(Reminder.id == reminder_id)
			.with_for_update(of=Reminder, skip_locked=True)
		)
		reminder = result.scalar_one_or_none()
		if reminder is None:
			await cancel_reminder_notifications(reminder_id)
			return 0
		delivery_keys = await _load_reminder_delivery_keys(session, [reminder.id])
		completed_occurrences = await _load_completed_occurrences(
			session,
			[reminder.id],
		)
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
			await session.flush()
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
		await schedule_reminder_notifications(reminder_id, session=session)
	return len(notifications)
