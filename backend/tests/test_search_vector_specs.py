"""unit coverage for vector search resource specs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from api.schemas.calendar import CalendarEventUpdate
from api.schemas.reminder import ReminderUpdate
from api.v1.service.calendar.search import CALENDAR_EVENT_SPEC
from api.v1.service.reminders.search import REMINDER_SPEC


@pytest.mark.asyncio
async def test_vector_specs_revectorize_metadata_changes() -> None:
	start = datetime(2026, 1, 1, 9, tzinfo=UTC)

	assert await REMINDER_SPEC.should_revectorize(
		object(),
		ReminderUpdate(status="completed"),
		None,
	)
	assert await REMINDER_SPEC.should_revectorize(
		object(),
		ReminderUpdate(due_at=start),
		None,
	)
	assert await CALENDAR_EVENT_SPEC.should_revectorize(
		object(),
		CalendarEventUpdate(start_at=start, end_at=start + timedelta(hours=1)),
		None,
	)
	assert await CALENDAR_EVENT_SPEC.should_revectorize(
		object(),
		CalendarEventUpdate(recurrence=None),
		None,
	)
