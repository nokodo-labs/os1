"""tests for scheduled user session retention."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq.schedule_sources import LabelScheduleSource

from api.boot_settings import boot_settings
from api.models.user_session import UserSession
from api.settings import settings
from api.taskiq import broker
from api.v1.tasks import user_sessions as user_session_tasks
from api.v1.tasks.user_sessions import (
	USER_SESSION_PURGE_SCHEDULE_ID,
	USER_SESSION_PURGE_TASK,
	clear_disabled_user_session_purge_schedule,
	run_user_session_purge,
)


class _FakeScheduleSource:
	def __init__(self) -> None:
		self.deleted: list[str] = []

	async def delete_schedule(self, schedule_id: str) -> None:
		self.deleted.append(schedule_id)


def _auth_headers(auth: dict[str, object]) -> dict[str, str]:
	headers = auth["headers"]
	assert isinstance(headers, dict)
	return {str(key): str(value) for key, value in headers.items()}


def _auth_user_id(auth: dict[str, object]) -> str:
	user = auth["user"]
	assert isinstance(user, dict)
	typed_user = {str(key): value for key, value in user.items()}
	return str(typed_user["id"])


async def _create_session(
	db_session: AsyncSession,
	user_id: str,
	expires_at: datetime,
	revoked_at: datetime | None = None,
) -> UserSession:
	row = UserSession(
		user_id=user_id,
		current_jti=f"purge-{expires_at.timestamp()}-{revoked_at}",
		expires_at=expires_at,
		revoked_at=revoked_at,
	)
	db_session.add(row)
	await db_session.flush()
	return row


@pytest.mark.asyncio
async def test_user_session_purge_skips_when_disabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setenv("NOKODO__TASKS__USER_SESSION_PURGE__ENABLED", "false")
	result = await run_user_session_purge(respect_enabled=True)

	assert result == {"skipped": True, "reason": "disabled", "purged": 0}


@pytest.mark.asyncio
async def test_user_session_purge_deletes_only_expired_past_grace(
	db_session: AsyncSession,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	now = datetime.now(UTC)
	user_id = _auth_user_id(user_auth)
	old_expired = await _create_session(
		db_session,
		user_id,
		now - timedelta(days=31),
	)
	recent_expired = await _create_session(
		db_session,
		user_id,
		now - timedelta(days=29),
	)
	revoked_unexpired = await _create_session(
		db_session,
		user_id,
		now + timedelta(days=1),
		revoked_at=now - timedelta(days=31),
	)
	await db_session.commit()
	ids = {old_expired.id, recent_expired.id, revoked_unexpired.id}
	expected_remaining = {recent_expired.id, revoked_unexpired.id}
	monkeypatch.setattr(settings.tasks.user_session_purge, "grace_period_days", 30)

	result = await run_user_session_purge(batch_size=10, respect_enabled=False)

	assert result["purged"] == 1
	db_session.expire_all()
	remaining = await db_session.scalars(
		select(UserSession.id).where(UserSession.id.in_(ids))
	)
	assert set(remaining.all()) == expected_remaining


@pytest.mark.asyncio
async def test_user_session_purge_respects_batch_size(
	db_session: AsyncSession,
	user_auth: dict[str, object],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	now = datetime.now(UTC)
	user_id = _auth_user_id(user_auth)
	for days in (40, 41, 42):
		await _create_session(db_session, user_id, now - timedelta(days=days))
	await db_session.commit()
	monkeypatch.setattr(settings.tasks.user_session_purge, "grace_period_days", 30)

	result = await run_user_session_purge(batch_size=2, respect_enabled=False)

	assert result["purged"] == 2


@pytest.mark.asyncio
async def test_disabled_user_session_schedule_cleared_before_startup(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	monkeypatch.setattr(boot_settings, "TESTING", False)
	monkeypatch.setenv("NOKODO__TASKS__USER_SESSION_PURGE__ENABLED", "false")
	fake_source = _FakeScheduleSource()
	monkeypatch.setattr(user_session_tasks, "redis_schedule_source", fake_source)

	cleared = await clear_disabled_user_session_purge_schedule()

	assert cleared is True
	assert fake_source.deleted == [USER_SESSION_PURGE_SCHEDULE_ID]


@pytest.mark.asyncio
async def test_user_session_purge_is_not_a_static_label_schedule() -> None:
	source = LabelScheduleSource(broker)
	await source.startup()
	schedules = await source.get_schedules()
	assert USER_SESSION_PURGE_TASK not in {schedule.task_name for schedule in schedules}


@pytest.mark.asyncio
async def test_user_session_purge_endpoint_requires_admin(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	response = await client.post(
		"/v1/users/sessions/purge/run",
		headers=_auth_headers(user_auth),
	)

	assert response.status_code == 403


@pytest.mark.asyncio
async def test_user_session_purge_endpoint_runs_for_admin(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	response = await client.post(
		"/v1/users/sessions/purge/run?batch_size=5",
		headers=_auth_headers(admin_auth),
	)

	assert response.status_code == 200
	assert response.json()["batch_size"] == 5
