"""scheduled items and recurrence coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Self
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.models.calendar import Calendar, CalendarEvent, CalendarEventOverride
from api.models.event import Event
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.reminder import Reminder, ReminderList, ReminderOverride, ReminderStatus
from api.models.user import User
from api.schemas.scheduled_item import (
	Recurrence,
	ScheduledItem,
	ScheduledItemListFilters,
)
from api.v1.routers.scheduled_items import list_scheduled_items
from api.v1.service.auth import Principal
from api.v1.service.calendar import events as calendar_events_service
from api.v1.service.calendar.cache import (
	get_cached_calendar_event_items,
	invalidate_calendar_event_scheduled_items,
	invalidate_calendar_scheduled_items,
	set_cached_calendar_event_items,
)
from api.v1.service.chat.tools.calendar import CalendarEventWriteInput
from api.v1.service.chat.tools.reminders import ReminderWriteInput
from api.v1.service.reminders import core as reminder_core_service
from api.v1.service.reminders.cache import (
	get_cached_reminder_items,
	invalidate_reminder_list_scheduled_items,
	invalidate_reminder_scheduled_items,
	set_cached_reminder_items,
)
from api.v1.service.scheduling.recurrence import (
	expand_occurrence_starts,
	occurrence_exists,
)
from api.v1.tasks import calendar as calendar_tasks
from api.v1.tasks import reminders as reminder_tasks
from api.v1.tasks.calendar import (
	_calendar_event_occurrence_starts,
	dispatch_calendar_event_notification,
	dispatch_due_calendar_notifications,
)
from api.v1.tasks.reminders import (
	_reminder_notification_occurrences,
	_reminder_occurrence_due_at,
	dispatch_due_reminder_notifications,
	dispatch_reminder_notification,
)
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import TypeID, new_typeid


def utc_datetime(
	year: int,
	month: int,
	day: int,
	hour: int = 0,
	minute: int = 0,
) -> datetime:
	return datetime(year, month, day, hour, minute, tzinfo=UTC)


def parse_api_datetime(value: str) -> datetime:
	return datetime.fromisoformat(value.replace("Z", "+00:00"))


def recurrence_payload(rule: str) -> dict[str, object]:
	return {"rrule": [rule], "rdate": [], "exdate": [], "timezone": "UTC"}


def ceil_to_minute(value: datetime) -> datetime:
	if value.second == 0 and value.microsecond == 0:
		return value
	return value.replace(second=0, microsecond=0) + timedelta(minutes=1)


def build_user(email: str, username: str, is_superuser: bool = False) -> User:
	return User(
		email=email,
		username=username,
		hashed_password=hash_password("password"),
		is_active=True,
		is_superuser=is_superuser,
	)


def find_item(
	items: list[dict[str, object]],
	kind: str,
	original_occurrence_at: datetime,
) -> dict[str, object]:
	for item in items:
		if item["kind"] != kind:
			continue
		value = item["original_occurrence_at"]
		assert isinstance(value, str)
		if parse_api_datetime(value) == original_occurrence_at:
			return item
	raise AssertionError(f"missing {kind} item at {original_occurrence_at.isoformat()}")


class FakeScheduleSource:
	def __init__(self) -> None:
		self.deleted: list[str] = []

	async def delete_schedule(self, schedule_id: str) -> None:
		self.deleted.append(schedule_id)


class FakeKicker:
	def __init__(self) -> None:
		self.schedule_id: str | None = None
		self.scheduled: list[tuple[str, datetime, TypeID]] = []

	def with_schedule_id(self, schedule_id: str) -> Self:
		self.schedule_id = schedule_id
		return self

	async def schedule_by_time(
		self,
		source: object,
		schedule_at: datetime,
		resource_id: TypeID,
	) -> None:
		_ = source
		if self.schedule_id is None:
			raise AssertionError("schedule id was not set")
		self.scheduled.append((self.schedule_id, schedule_at, resource_id))


class FakeTask:
	def __init__(self) -> None:
		self.kicker_instance = FakeKicker()

	def kicker(self) -> FakeKicker:
		return self.kicker_instance


def test_recurrence_expands_daily_weekly_monthly_and_exdates() -> None:
	anchor = utc_datetime(2026, 1, 1, 9)
	window_start = utc_datetime(2026, 1, 1)
	window_end = utc_datetime(2026, 4, 1)

	daily = expand_occurrence_starts(
		anchor,
		Recurrence(
			rrule=["FREQ=DAILY;COUNT=3"],
			exdate=[utc_datetime(2026, 1, 2, 9)],
			timezone="UTC",
		),
		window_start,
		window_end,
	)
	weekly = expand_occurrence_starts(
		utc_datetime(2026, 1, 5, 9),
		Recurrence(rrule=["FREQ=WEEKLY;COUNT=3"], timezone="UTC"),
		window_start,
		window_end,
	)
	monthly = expand_occurrence_starts(
		utc_datetime(2026, 1, 15, 9),
		Recurrence(rrule=["FREQ=MONTHLY;COUNT=3"], timezone="UTC"),
		window_start,
		window_end,
	)

	assert daily == [utc_datetime(2026, 1, 1, 9), utc_datetime(2026, 1, 3, 9)]
	assert weekly == [
		utc_datetime(2026, 1, 5, 9),
		utc_datetime(2026, 1, 12, 9),
		utc_datetime(2026, 1, 19, 9),
	]
	assert monthly == [
		utc_datetime(2026, 1, 15, 9),
		utc_datetime(2026, 2, 15, 9),
		utc_datetime(2026, 3, 15, 9),
	]
	assert occurrence_exists(
		anchor,
		Recurrence(rrule=["FREQ=DAILY;COUNT=3"], timezone="UTC"),
		utc_datetime(2026, 1, 2, 9),
	)
	assert not occurrence_exists(
		anchor,
		Recurrence(rrule=["FREQ=DAILY;COUNT=3"], timezone="UTC"),
		utc_datetime(2026, 1, 5, 9),
	)


def test_recurrence_expansion_preserves_wall_time_across_dst() -> None:
	timezone = ZoneInfo("America/New_York")
	anchor = datetime(2026, 3, 7, 9, tzinfo=timezone)
	occurrences = expand_occurrence_starts(
		anchor,
		Recurrence(
			rrule=["FREQ=DAILY;COUNT=3"],
			timezone="America/New_York",
		),
		datetime(2026, 3, 7, tzinfo=timezone),
		datetime(2026, 3, 10, tzinfo=timezone),
	)

	assert [occurrence.hour for occurrence in occurrences] == [9, 9, 9]
	assert occurrences[0].utcoffset() != occurrences[-1].utcoffset()


def test_scheduled_models_do_not_have_soft_delete_columns() -> None:
	models = (
		Calendar,
		CalendarEvent,
		CalendarEventOverride,
		ReminderList,
		Reminder,
		ReminderOverride,
	)
	for model in models:
		assert "deleted_at" not in model.__table__.columns
		assert not hasattr(model, "soft_delete")


@pytest.mark.asyncio
async def test_alert_notifications_link_origin_resource_through_event(
	db_session: AsyncSession,
) -> None:
	owner = build_user("alert-owner@example.com", "alert_owner")
	db_session.add(owner)
	await db_session.flush()

	now = datetime.now(tz=UTC)
	calendar = Calendar(
		owner_id=owner.id,
		name="alerts",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=False,
		timezone=None,
	)
	calendar_event = CalendarEvent(
		owner_id=owner.id,
		calendar=calendar,
		title="alert event",
		description=None,
		start_at=now - timedelta(minutes=1),
		end_at=now + timedelta(minutes=59),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[0],
		location=None,
		virtual_url=None,
		labels=[],
	)
	reminder_list = ReminderList(
		owner_id=owner.id,
		name="alert reminders",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	reminder = Reminder(
		owner_id=owner.id,
		reminder_list=reminder_list,
		title="alert reminder",
		description=None,
		due_at=None,
		remind_at=now - timedelta(minutes=1),
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	db_session.add_all([calendar, calendar_event, reminder_list, reminder])
	await db_session.commit()

	assert await dispatch_due_calendar_notifications() == 1
	assert await dispatch_due_reminder_notifications() == 1

	calendar_result = await db_session.execute(
		select(Notification, Event)
		.join(Event, Notification.event_id == Event.id)
		.where(Event.calendar_event_id == calendar_event.id)
	)
	calendar_notification, calendar_notification_event = calendar_result.one()
	assert calendar_notification_event.calendar_event_id == calendar_event.id
	assert calendar_notification_event.calendar_id is None
	assert calendar_notification.event_id == calendar_notification_event.id
	assert calendar_notification.notify_at == calendar_event.start_at
	assert calendar_notification.delivery_key == (
		f"calendar:{owner.id}:{calendar_event.id}:"
		f"{calendar_event.start_at.isoformat()}:0"
	)

	reminder_result = await db_session.execute(
		select(Notification, Event)
		.join(Event, Notification.event_id == Event.id)
		.where(Event.reminder_id == reminder.id)
	)
	reminder_notification, reminder_notification_event = reminder_result.one()
	assert reminder_notification_event.reminder_id == reminder.id
	assert reminder_notification_event.reminder_list_id is None
	assert reminder_notification.event_id == reminder_notification_event.id
	assert reminder.remind_at is not None
	assert reminder_notification.notify_at == reminder.remind_at
	assert reminder_notification.delivery_key == (
		f"reminder:{owner.id}:{reminder.id}:{reminder.remind_at.isoformat()}"
	)

	await db_session.refresh(calendar_event)
	await db_session.refresh(reminder)
	assert "calendar_notification_sent_keys" not in calendar_event.metadata_
	assert "reminder_notification_sent_keys" not in reminder.metadata_
	assert await dispatch_due_calendar_notifications() == 0
	assert await dispatch_due_reminder_notifications() == 0


@pytest.mark.asyncio
async def test_child_reminders_dispatch_independent_notifications(
	db_session: AsyncSession,
) -> None:
	owner = build_user("subtask-alert-owner@example.com", "subtask_alert_owner")
	db_session.add(owner)
	await db_session.flush()

	now = datetime.now(tz=UTC)
	reminder_list = ReminderList(
		owner_id=owner.id,
		name="subtask alerts",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	parent = Reminder(
		owner_id=owner.id,
		reminder_list=reminder_list,
		title="parent reminder",
		description=None,
		due_at=None,
		remind_at=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	child = Reminder(
		owner_id=owner.id,
		reminder_list=reminder_list,
		parent=parent,
		title="child reminder",
		description=None,
		due_at=None,
		remind_at=now - timedelta(minutes=1),
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	db_session.add_all([reminder_list, parent, child])
	await db_session.commit()

	assert await dispatch_due_reminder_notifications() == 1
	result = await db_session.execute(
		select(Notification)
		.join(Event, Notification.event_id == Event.id)
		.where(Event.reminder_id == child.id)
	)
	notification = result.scalar_one()
	assert notification.notify_at == child.remind_at


@pytest.mark.asyncio
async def test_resource_notification_tasks_dispatch_idempotently(
	db_session: AsyncSession,
) -> None:
	owner = build_user("resource-alert-owner@example.com", "resource_alert_owner")
	db_session.add(owner)
	await db_session.flush()

	now = datetime.now(tz=UTC)
	calendar = Calendar(
		owner_id=owner.id,
		name="resource alerts",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=False,
		timezone=None,
	)
	calendar_event = CalendarEvent(
		owner_id=owner.id,
		calendar=calendar,
		title="resource event",
		description=None,
		start_at=now - timedelta(minutes=1),
		end_at=now + timedelta(minutes=59),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[0],
		location=None,
		virtual_url=None,
		labels=[],
	)
	reminder_list = ReminderList(
		owner_id=owner.id,
		name="resource reminders",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	reminder = Reminder(
		owner_id=owner.id,
		reminder_list=reminder_list,
		title="resource reminder",
		description=None,
		due_at=None,
		remind_at=now - timedelta(minutes=1),
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	db_session.add_all([calendar, calendar_event, reminder_list, reminder])
	await db_session.commit()

	assert await dispatch_calendar_event_notification(calendar_event.id) == 1
	assert await dispatch_reminder_notification(reminder.id) == 1
	assert await dispatch_calendar_event_notification(calendar_event.id) == 0
	assert await dispatch_reminder_notification(reminder.id) == 0


@pytest.mark.asyncio
async def test_dynamic_notification_schedules_use_resource_schedule_ids(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(boot_settings, "TESTING", False)
	reminder_source = FakeScheduleSource()
	calendar_source = FakeScheduleSource()
	reminder_task = FakeTask()
	calendar_task = FakeTask()
	monkeypatch.setattr(reminder_tasks, "redis_schedule_source", reminder_source)
	monkeypatch.setattr(calendar_tasks, "redis_schedule_source", calendar_source)
	monkeypatch.setattr(
		reminder_tasks,
		"dispatch_reminder_notification",
		reminder_task,
	)
	monkeypatch.setattr(
		calendar_tasks,
		"dispatch_calendar_event_notification",
		calendar_task,
	)

	owner = build_user("dynamic-alert-owner@example.com", "dynamic_alert_owner")
	db_session.add(owner)
	await db_session.flush()
	now = datetime.now(tz=UTC)
	remind_at = now + timedelta(minutes=12, seconds=11, microseconds=1)
	event_start = now + timedelta(hours=2, seconds=17, microseconds=1)
	notify_at = event_start - timedelta(minutes=15)
	calendar = Calendar(
		owner_id=owner.id,
		name="dynamic alerts",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=False,
		timezone=None,
	)
	calendar_event = CalendarEvent(
		owner_id=owner.id,
		calendar=calendar,
		title="dynamic event",
		description=None,
		start_at=event_start,
		end_at=event_start + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[15],
		location=None,
		virtual_url=None,
		labels=[],
	)
	reminder_list = ReminderList(
		owner_id=owner.id,
		name="dynamic reminders",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	reminder = Reminder(
		owner_id=owner.id,
		reminder_list=reminder_list,
		title="dynamic reminder",
		description=None,
		due_at=None,
		remind_at=remind_at,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	db_session.add_all([calendar, calendar_event, reminder_list, reminder])
	await db_session.flush()

	await reminder_tasks.schedule_reminder_notifications(
		reminder.id,
		session=db_session,
	)
	await calendar_tasks.schedule_calendar_event_notifications(
		calendar_event.id,
		session=db_session,
	)
	await reminder_tasks.cancel_reminder_notifications(reminder.id)
	await calendar_tasks.cancel_calendar_event_notifications(calendar_event.id)

	reminder_schedule_id = f"notifications:reminder:{reminder.id}"
	calendar_schedule_id = f"notifications:calendar-event:{calendar_event.id}"
	assert reminder_source.deleted == [reminder_schedule_id, reminder_schedule_id]
	assert calendar_source.deleted == [calendar_schedule_id, calendar_schedule_id]
	assert reminder_task.kicker_instance.scheduled == [
		(reminder_schedule_id, ceil_to_minute(remind_at), reminder.id)
	]
	assert calendar_task.kicker_instance.scheduled == [
		(calendar_schedule_id, ceil_to_minute(notify_at), calendar_event.id)
	]


@pytest.mark.asyncio
async def test_scheduled_projection_cache_invalidation_is_resource_scoped() -> None:
	calendar_id = new_typeid("cal")
	calendar_event_id = new_typeid("calev")
	reminder_list_id = new_typeid("reml")
	reminder_id = new_typeid("rem")
	start_at = utc_datetime(2026, 10, 1, 9)
	end_at = utc_datetime(2026, 10, 1, 10)
	calendar_item = ScheduledItem(
		kind="event",
		id="event-cache-item",
		parent_id=calendar_event_id,
		container_id=calendar_id,
		calendar_id=calendar_id,
		original_occurrence_at=start_at,
		effective_start_at=start_at,
		effective_end_at=end_at,
		all_day=False,
		title="cached event",
		status="scheduled",
	)
	reminder_item = ScheduledItem(
		kind="reminder",
		id="reminder-cache-item",
		parent_id=reminder_id,
		container_id=reminder_list_id,
		reminder_list_id=reminder_list_id,
		original_occurrence_at=start_at,
		effective_start_at=start_at,
		all_day=False,
		title="cached reminder",
		status=ReminderStatus.PENDING,
	)

	await set_cached_calendar_event_items(
		calendar_event_id,
		calendar_id,
		start_at,
		end_at,
		[calendar_item],
	)
	await set_cached_reminder_items(
		reminder_id,
		reminder_list_id,
		start_at,
		end_at,
		False,
		[reminder_item],
	)
	cached_calendar_items = await get_cached_calendar_event_items(
		calendar_event_id,
		start_at,
		end_at,
	)
	assert cached_calendar_items == [calendar_item]
	assert await get_cached_reminder_items(
		reminder_id,
		start_at,
		end_at,
		False,
	) == [reminder_item]

	await invalidate_calendar_event_scheduled_items(calendar_event_id)
	assert (
		await get_cached_calendar_event_items(calendar_event_id, start_at, end_at)
		is None
	)
	await set_cached_calendar_event_items(
		calendar_event_id,
		calendar_id,
		start_at,
		end_at,
		[calendar_item],
	)
	await invalidate_calendar_scheduled_items(calendar_id)
	assert (
		await get_cached_calendar_event_items(calendar_event_id, start_at, end_at)
		is None
	)

	await invalidate_reminder_scheduled_items(reminder_id)
	assert (
		await get_cached_reminder_items(
			reminder_id,
			start_at,
			end_at,
			False,
		)
		is None
	)
	await set_cached_reminder_items(
		reminder_id,
		reminder_list_id,
		start_at,
		end_at,
		False,
		[reminder_item],
	)
	await invalidate_reminder_list_scheduled_items(reminder_list_id)
	assert (
		await get_cached_reminder_items(
			reminder_id,
			start_at,
			end_at,
			False,
		)
		is None
	)


@pytest.mark.asyncio
async def test_scheduled_projection_cache_is_queried_after_access_filtering(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = build_user("cache-owner@example.com", "cache_owner")
	other = build_user("cache-other@example.com", "cache_other")
	db_session.add_all([owner, other])
	await db_session.flush()
	now = utc_datetime(2026, 11, 1, 9)
	owner_calendar = Calendar(
		owner_id=owner.id,
		name="owner calendar",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=False,
		timezone=None,
	)
	other_calendar = Calendar(
		owner_id=other.id,
		name="other calendar",
		description=None,
		color="#d45446",
		position=0.0,
		is_default=False,
		timezone=None,
	)
	owner_event = CalendarEvent(
		owner_id=owner.id,
		calendar=owner_calendar,
		title="owner event",
		description=None,
		start_at=now,
		end_at=now + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[],
		location=None,
		virtual_url=None,
		labels=[],
	)
	other_event = CalendarEvent(
		owner_id=other.id,
		calendar=other_calendar,
		title="other event",
		description=None,
		start_at=now,
		end_at=now + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[],
		location=None,
		virtual_url=None,
		labels=[],
	)
	owner_list = ReminderList(
		owner_id=owner.id,
		name="owner reminders",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	other_list = ReminderList(
		owner_id=other.id,
		name="other reminders",
		description=None,
		color="#22c55e",
		icon=None,
		position=0.0,
		is_default=False,
	)
	owner_reminder = Reminder(
		owner_id=owner.id,
		reminder_list=owner_list,
		title="owner reminder",
		description=None,
		due_at=now,
		remind_at=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	owner_child_reminder = Reminder(
		owner_id=owner.id,
		reminder_list=owner_list,
		parent=owner_reminder,
		title="owner child reminder",
		description=None,
		due_at=now + timedelta(minutes=30),
		remind_at=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	other_reminder = Reminder(
		owner_id=other.id,
		reminder_list=other_list,
		title="other reminder",
		description=None,
		due_at=now,
		remind_at=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		status=ReminderStatus.PENDING,
		completed_at=None,
		position=0.0,
	)
	db_session.add_all(
		[
			owner_calendar,
			other_calendar,
			owner_event,
			other_event,
			owner_list,
			other_list,
			owner_reminder,
			owner_child_reminder,
			other_reminder,
		]
	)
	await db_session.commit()

	queried_calendar_event_ids: list[str] = []
	queried_reminder_ids: list[str] = []

	async def fake_calendar_cache_get(
		event_id: TypeID,
		start_at: datetime,
		end_at: datetime,
	) -> None:
		_ = (start_at, end_at)
		queried_calendar_event_ids.append(str(event_id))
		return None

	async def fake_calendar_cache_set(
		event_id: TypeID,
		calendar_id: TypeID,
		start_at: datetime,
		end_at: datetime,
		items: list[ScheduledItem],
	) -> None:
		_ = (event_id, calendar_id, start_at, end_at, items)

	async def fake_reminder_cache_get(
		reminder_id: TypeID,
		start_at: datetime,
		end_at: datetime,
		include_completed: bool,
	) -> None:
		_ = (start_at, end_at, include_completed)
		queried_reminder_ids.append(str(reminder_id))
		return None

	async def fake_reminder_cache_set(
		reminder_id: TypeID,
		list_id: TypeID,
		start_at: datetime,
		end_at: datetime,
		include_completed: bool,
		items: list[ScheduledItem],
	) -> None:
		_ = (reminder_id, list_id, start_at, end_at, include_completed, items)

	monkeypatch.setattr(
		calendar_events_service,
		"get_cached_calendar_event_items",
		fake_calendar_cache_get,
	)
	monkeypatch.setattr(
		calendar_events_service,
		"set_cached_calendar_event_items",
		fake_calendar_cache_set,
	)
	monkeypatch.setattr(
		reminder_core_service,
		"get_cached_reminder_items",
		fake_reminder_cache_get,
	)
	monkeypatch.setattr(
		reminder_core_service,
		"set_cached_reminder_items",
		fake_reminder_cache_set,
	)
	principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	items = await list_scheduled_items(
		filters=ScheduledItemListFilters(
			start_at=now - timedelta(hours=1),
			end_at=now + timedelta(hours=2),
		),
		limit=2000,
		principal=principal,
		db=db_session,
	)

	assert {item.parent_id for item in items} == {
		owner_event.id,
		owner_reminder.id,
		owner_child_reminder.id,
	}
	assert queried_calendar_event_ids == [str(owner_event.id)]
	assert queried_reminder_ids == [
		str(owner_reminder.id),
		str(owner_child_reminder.id),
	]


@pytest.mark.asyncio
async def test_event_resource_links_use_nearest_emitting_resource(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	async def load_event(event_type: EventType, resource_id: str) -> Event:
		result = await db_session.execute(
			select(Event)
			.where(Event.type == event_type.value)
			.order_by(Event.created_at.desc())
		)
		for event in result.scalars().all():
			if event.data.get("id") == resource_id:
				return event
		raise AssertionError(f"missing event {event_type.value} for {resource_id}")

	calendar_response = await client.post(
		"/v1/calendars",
		headers=headers,
		json={"name": "link policy", "color": "#d45446"},
	)
	assert calendar_response.status_code == 201
	calendar_id = calendar_response.json()["id"]
	calendar_created = await load_event(EventType.CALENDAR_CREATED, calendar_id)
	assert calendar_created.calendar_id == calendar_id
	assert calendar_created.calendar_event_id is None
	assert calendar_created.reminder_list_id is None
	assert calendar_created.reminder_id is None

	event_response = await client.post(
		f"/v1/calendars/{calendar_id}/events",
		headers=headers,
		json={
			"title": "review links",
			"start_at": utc_datetime(2026, 9, 1, 9).isoformat(),
			"end_at": utc_datetime(2026, 9, 1, 10).isoformat(),
		},
	)
	assert event_response.status_code == 201
	calendar_event_id = event_response.json()["id"]
	calendar_event_created = await load_event(
		EventType.CALENDAR_EVENT_CREATED,
		calendar_event_id,
	)
	assert calendar_event_created.calendar_event_id == calendar_event_id
	assert calendar_event_created.calendar_id is None
	assert calendar_event_created.reminder_list_id is None
	assert calendar_event_created.reminder_id is None

	list_response = await client.post(
		"/v1/reminder-lists",
		headers=headers,
		json={"name": "link reminders", "color": "#22c55e"},
	)
	assert list_response.status_code == 201
	list_id = list_response.json()["id"]
	list_created = await load_event(EventType.REMINDER_LIST_CREATED, list_id)
	assert list_created.reminder_list_id == list_id
	assert list_created.reminder_id is None
	assert list_created.calendar_id is None
	assert list_created.calendar_event_id is None

	reminder_response = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=headers,
		json={"title": "check links"},
	)
	assert reminder_response.status_code == 201
	reminder_id = reminder_response.json()["id"]
	reminder_created = await load_event(EventType.REMINDER_CREATED, reminder_id)
	assert reminder_created.reminder_id == reminder_id
	assert reminder_created.reminder_list_id is None
	assert reminder_created.calendar_id is None
	assert reminder_created.calendar_event_id is None


def test_reminder_notification_occurrences_skip_completed_instances() -> None:
	reminder_id = new_typeid("rem")
	remind_at = utc_datetime(2026, 6, 1, 8)
	due_at = utc_datetime(2026, 6, 1, 9)
	reminder = Reminder(
		id=reminder_id,
		owner_id=new_typeid("user"),
		list_id=new_typeid("reml"),
		title="water plants",
		description=None,
		due_at=due_at,
		remind_at=remind_at,
		recurrence=recurrence_payload("FREQ=DAILY;COUNT=3"),
		status=ReminderStatus.PENDING,
	)
	completed_occurrences = {(reminder_id, remind_at)}

	occurrences = _reminder_notification_occurrences(
		reminder,
		completed_occurrences,
		utc_datetime(2026, 6, 2, 8),
	)

	assert occurrences == [utc_datetime(2026, 6, 2, 8)]
	assert _reminder_occurrence_due_at(reminder, occurrences[0]) == utc_datetime(
		2026,
		6,
		2,
		9,
	)


def test_calendar_notification_occurrences_include_moved_instances() -> None:
	event_id = new_typeid("calev")
	start_at = utc_datetime(2026, 5, 1, 9)
	calendar_event = CalendarEvent(
		id=event_id,
		owner_id=new_typeid("user"),
		calendar_id=new_typeid("cal"),
		title="standup",
		description=None,
		start_at=start_at,
		end_at=start_at + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=recurrence_payload("FREQ=DAILY;COUNT=3"),
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[60],
		location=None,
		virtual_url=None,
		labels=[],
	)
	moved_original = start_at + timedelta(days=2)
	override = CalendarEventOverride(
		event_id=event_id,
		original_occurrence_at=moved_original,
		cancelled_at=None,
		new_start_at=utc_datetime(2026, 5, 2, 8, 30),
		new_end_at=utc_datetime(2026, 5, 2, 9, 30),
		payload_patch={},
	)

	occurrences = _calendar_event_occurrence_starts(
		calendar_event,
		{(event_id, moved_original): override},
		utc_datetime(2026, 5, 2, 8),
	)

	assert start_at in occurrences
	assert start_at + timedelta(days=1) in occurrences
	assert moved_original in occurrences


def test_calendar_notification_occurrences_include_two_day_offsets() -> None:
	start_at = utc_datetime(2026, 5, 3, 9)
	calendar_event = CalendarEvent(
		id=new_typeid("calev"),
		owner_id=new_typeid("user"),
		calendar_id=new_typeid("cal"),
		title="release review",
		description=None,
		start_at=start_at,
		end_at=start_at + timedelta(hours=1),
		all_day=False,
		timezone=None,
		recurrence=None,
		recurrence_until=None,
		series_origin_id=None,
		notification_offsets=[2880],
		location=None,
		virtual_url=None,
		labels=[],
	)

	occurrences = _calendar_event_occurrence_starts(
		calendar_event,
		{},
		utc_datetime(2026, 5, 1, 9),
	)

	assert occurrences == [start_at]


def test_chat_tool_recurrence_inputs_preserve_compound_rules() -> None:
	recurrence = {
		"rrule": ["FREQ=WEEKLY;BYDAY=MO", "FREQ=WEEKLY;BYDAY=WE"],
		"rdate": [utc_datetime(2026, 5, 8, 9).isoformat()],
		"exdate": [utc_datetime(2026, 5, 5, 9).isoformat()],
		"timezone": "UTC",
	}
	calendar_input = CalendarEventWriteInput.model_validate(
		{
			"title": "planning",
			"start_at": utc_datetime(2026, 5, 4, 9).isoformat(),
			"end_at": utc_datetime(2026, 5, 4, 10).isoformat(),
			"recurrence": recurrence,
		}
	)
	reminder_input = ReminderWriteInput.model_validate(
		{
			"title": "prep agenda",
			"remind_at": utc_datetime(2026, 5, 4, 8).isoformat(),
			"recurrence": recurrence,
		}
	)

	assert calendar_input.recurrence is not None
	assert calendar_input.recurrence.rrule == recurrence["rrule"]
	assert reminder_input.recurrence is not None
	assert reminder_input.recurrence.rrule == recurrence["rrule"]


@pytest.mark.asyncio
async def test_event_occurrence_edit_and_cancel_project_to_scheduled_items(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	start_at = utc_datetime(2026, 5, 1, 9)
	end_at = start_at + timedelta(hours=1)
	window_start = utc_datetime(2026, 5, 1)
	window_end = utc_datetime(2026, 5, 5)

	calendar_response = await client.post(
		"/v1/calendars",
		headers=headers,
		json={"name": "events", "color": "#d45446"},
	)
	assert calendar_response.status_code == 201
	calendar_id = calendar_response.json()["id"]

	event_response = await client.post(
		f"/v1/calendars/{calendar_id}/events",
		headers=headers,
		json={
			"title": "standup",
			"start_at": start_at.isoformat(),
			"end_at": end_at.isoformat(),
			"recurrence": recurrence_payload("FREQ=DAILY;COUNT=3"),
		},
	)
	assert event_response.status_code == 201
	event_id = event_response.json()["id"]

	scheduled_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
		},
	)
	assert scheduled_response.status_code == 200
	items = scheduled_response.json()
	assert len([item for item in items if item["kind"] == "event"]) == 3

	edited_original = start_at + timedelta(days=1)
	edited_start = edited_original + timedelta(hours=2)
	edited_end = edited_start + timedelta(hours=1)
	edit_response = await client.patch(
		f"/v1/calendars/{calendar_id}/events/{event_id}/occurrence",
		headers=headers,
		json={
			"original_occurrence_at": edited_original.isoformat(),
			"new_start_at": edited_start.isoformat(),
			"new_end_at": edited_end.isoformat(),
			"title": "shifted standup",
		},
	)
	assert edit_response.status_code == 200

	cancelled_original = start_at + timedelta(days=2)
	cancel_response = await client.post(
		f"/v1/calendars/{calendar_id}/events/{event_id}/occurrence/cancel",
		headers=headers,
		json={"original_occurrence_at": cancelled_original.isoformat()},
	)
	assert cancel_response.status_code == 204

	projected_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
		},
	)
	assert projected_response.status_code == 200
	projected_items = projected_response.json()
	edited_item = find_item(
		projected_items,
		kind="event",
		original_occurrence_at=edited_original,
	)
	cancelled_item = find_item(
		projected_items,
		kind="event",
		original_occurrence_at=cancelled_original,
	)

	assert edited_item["title"] == "shifted standup"
	assert parse_api_datetime(str(edited_item["effective_start_at"])) == edited_start
	assert cancelled_item["status"] == "cancelled"
	assert cancelled_item["readonly"] is True


@pytest.mark.asyncio
async def test_reminder_occurrence_completion_only_completes_one_instance(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	due_at = utc_datetime(2026, 6, 1, 8)
	window_start = utc_datetime(2026, 6, 1)
	window_end = utc_datetime(2026, 6, 4)

	list_response = await client.post(
		"/v1/reminder-lists",
		headers=headers,
		json={"name": "scheduled", "color": "#22c55e"},
	)
	assert list_response.status_code == 201
	list_id = list_response.json()["id"]

	reminder_response = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=headers,
		json={
			"title": "water plants",
			"due_at": due_at.isoformat(),
			"recurrence": recurrence_payload("FREQ=DAILY;COUNT=2"),
		},
	)
	assert reminder_response.status_code == 201
	reminder_id = reminder_response.json()["id"]
	assert reminder_response.json()["list_id"] == list_id

	master_complete_response = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders/{reminder_id}/complete",
		headers=headers,
	)
	assert master_complete_response.status_code == 409

	complete_response = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders/{reminder_id}/occurrence/complete",
		headers=headers,
		json={"original_occurrence_at": due_at.isoformat()},
	)
	assert complete_response.status_code == 200
	assert complete_response.json()["status"] == "completed"

	pending_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
		},
	)
	assert pending_response.status_code == 200
	pending_items = [
		item for item in pending_response.json() if item["kind"] == "reminder"
	]
	assert len(pending_items) == 1
	assert parse_api_datetime(
		pending_items[0]["original_occurrence_at"]
	) == due_at + timedelta(days=1)
	assert pending_items[0]["status"] == "pending"

	completed_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
			"include_completed": True,
		},
	)
	assert completed_response.status_code == 200
	completed_items = [
		item for item in completed_response.json() if item["kind"] == "reminder"
	]
	completed_item = find_item(
		completed_items,
		kind="reminder",
		original_occurrence_at=due_at,
	)
	assert len(completed_items) == 2
	assert completed_item["status"] == "completed"
	assert completed_item["completed_at"] is not None


@pytest.mark.asyncio
async def test_event_series_split_edits_following_occurrences(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	start_at = utc_datetime(2026, 7, 1, 9)
	window_start = utc_datetime(2026, 7, 1)
	window_end = utc_datetime(2026, 7, 6)

	calendar_response = await client.post(
		"/v1/calendars",
		headers=headers,
		json={"name": "series", "color": "#d45446"},
	)
	assert calendar_response.status_code == 201
	calendar_id = calendar_response.json()["id"]

	event_response = await client.post(
		f"/v1/calendars/{calendar_id}/events",
		headers=headers,
		json={
			"title": "standup",
			"start_at": start_at.isoformat(),
			"end_at": (start_at + timedelta(hours=1)).isoformat(),
			"recurrence": recurrence_payload("FREQ=DAILY;COUNT=4"),
		},
	)
	assert event_response.status_code == 201
	event_id = event_response.json()["id"]

	split_start = start_at + timedelta(days=1, hours=1)
	split_response = await client.patch(
		f"/v1/calendars/{calendar_id}/events/{event_id}/series/following",
		headers=headers,
		json={
			"original_occurrence_at": (start_at + timedelta(days=1)).isoformat(),
			"new_start_at": split_start.isoformat(),
			"new_end_at": (split_start + timedelta(hours=1)).isoformat(),
			"title": "shifted standup",
		},
	)
	assert split_response.status_code == 200
	new_event = split_response.json()
	assert new_event["id"] != event_id
	assert new_event["series_origin_id"] == event_id

	projected_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
		},
	)
	assert projected_response.status_code == 200
	event_items = [
		item for item in projected_response.json() if item["kind"] == "event"
	]
	assert [item["title"] for item in event_items].count("standup") == 1
	assert [item["title"] for item in event_items].count("shifted standup") == 3
	assert all(
		parse_api_datetime(item["effective_start_at"]) < utc_datetime(2026, 7, 5)
		for item in event_items
	)


@pytest.mark.asyncio
async def test_reminder_series_split_edits_following_occurrences(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	due_at = utc_datetime(2026, 8, 1, 8)
	window_start = utc_datetime(2026, 8, 1)
	window_end = utc_datetime(2026, 8, 5)

	list_response = await client.post(
		"/v1/reminder-lists",
		headers=headers,
		json={"name": "series reminders", "color": "#22c55e"},
	)
	assert list_response.status_code == 201
	list_id = list_response.json()["id"]

	reminder_response = await client.post(
		f"/v1/reminder-lists/{list_id}/reminders",
		headers=headers,
		json={
			"title": "water plants",
			"due_at": due_at.isoformat(),
			"recurrence": recurrence_payload("FREQ=DAILY;COUNT=3"),
		},
	)
	assert reminder_response.status_code == 201
	reminder_id = reminder_response.json()["id"]

	split_response = await client.patch(
		f"/v1/reminder-lists/{list_id}/reminders/{reminder_id}/series/following",
		headers=headers,
		json={
			"original_occurrence_at": (due_at + timedelta(days=1)).isoformat(),
			"title": "feed plants",
		},
	)
	assert split_response.status_code == 200
	new_reminder = split_response.json()
	assert new_reminder["id"] != reminder_id
	assert new_reminder["series_origin_id"] == reminder_id

	projected_response = await client.get(
		"/v1/scheduled-items",
		headers=headers,
		params={
			"start_at": window_start.isoformat(),
			"end_at": window_end.isoformat(),
		},
	)
	assert projected_response.status_code == 200
	reminder_items = [
		item for item in projected_response.json() if item["kind"] == "reminder"
	]
	assert [item["title"] for item in reminder_items].count("water plants") == 1
	assert [item["title"] for item in reminder_items].count("feed plants") == 2
	assert all(
		parse_api_datetime(item["effective_start_at"]) < utc_datetime(2026, 8, 4)
		for item in reminder_items
	)
