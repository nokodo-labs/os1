"""coverage for per-resource revectorize admin routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from api.v1.routers import calendar as calendar_router
from api.v1.routers import reminder_lists as reminder_lists_router


@pytest.mark.asyncio
async def test_reminders_and_calendar_events_revectorize_routes(
	client: AsyncClient,
	admin_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)

	async def fake_vectorize_reminders(*args: object, **kwargs: object) -> int:
		_ = (args, kwargs)
		return 7

	async def fake_vectorize_calendar_events(*args: object, **kwargs: object) -> int:
		_ = (args, kwargs)
		return 11

	monkeypatch.setattr(
		reminder_lists_router.reminder_service,
		"vectorize_all_reminders",
		fake_vectorize_reminders,
	)
	monkeypatch.setattr(
		calendar_router.calendar_service,
		"vectorize_all_calendar_events",
		fake_vectorize_calendar_events,
	)

	reminders_response = await client.post(
		"/v1/reminders/revectorize",
		headers=headers,
	)
	calendar_response = await client.post(
		"/v1/calendars/events/revectorize",
		headers=headers,
	)

	assert reminders_response.status_code == 200
	assert reminders_response.json() == {"vectorized": 7}
	assert calendar_response.status_code == 200
	assert calendar_response.json() == {"vectorized": 11}
