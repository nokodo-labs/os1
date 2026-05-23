"""unit coverage for vector search resource specs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.calendar import CalendarEvent
from api.models.project import Project
from api.models.reminder import Reminder, ReminderStatus
from api.schemas.calendar import CalendarEventUpdate
from api.schemas.project import ProjectUpdate
from api.schemas.reminder import ReminderUpdate
from api.v1.service.calendar.search import CALENDAR_EVENT_SPEC
from api.v1.service.projects import PROJECT_SPEC
from api.v1.service.reminders.search import REMINDER_SPEC


@pytest.mark.asyncio
async def test_vector_specs_revectorize_metadata_changes() -> None:
	start = datetime(2026, 1, 1, 9, tzinfo=UTC)
	session = AsyncSession()
	reminder = Reminder()
	calendar_event = CalendarEvent()
	project = Project()

	try:
		assert await REMINDER_SPEC.should_revectorize(
			reminder,
			ReminderUpdate(status=ReminderStatus.COMPLETED),
			session,
		)
		assert await REMINDER_SPEC.should_revectorize(
			reminder,
			ReminderUpdate(due_at=start),
			session,
		)
		assert await CALENDAR_EVENT_SPEC.should_revectorize(
			calendar_event,
			CalendarEventUpdate(start_at=start, end_at=start + timedelta(hours=1)),
			session,
		)
		assert await CALENDAR_EVENT_SPEC.should_revectorize(
			calendar_event,
			CalendarEventUpdate(recurrence=None),
			session,
		)
		assert await PROJECT_SPEC.should_revectorize(
			project,
			ProjectUpdate(name="renamed"),
			session,
		)
	finally:
		await session.close()
