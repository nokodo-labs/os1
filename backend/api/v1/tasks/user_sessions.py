"""user session maintenance tasks."""

import logging
from datetime import UTC, datetime, timedelta

from api.boot_settings import boot_settings
from api.database import async_session_local
from api.runtime import on_settings_reload
from api.settings import settings
from api.taskiq import broker, redis_schedule_source
from api.v1.service.authentication.sessions import purge_expired_sessions
from nokodo_ai.types.json import JSONObject


logger = logging.getLogger(__name__)


USER_SESSION_PURGE_TASK = "user_session.purge"
USER_SESSION_PURGE_SCHEDULE_ID = "user-session:purge"


async def run_user_session_purge(
	batch_size: int | None = None,
	respect_enabled: bool = True,
) -> JSONObject:
	"""purge one bounded batch of sessions past the retention period."""
	if respect_enabled:
		settings.reload()
	purge_settings = settings.tasks.user_session_purge
	if respect_enabled and not purge_settings.enabled:
		logger.info(
			"user session purge skipped reason=disabled schedule_id=%s",
			USER_SESSION_PURGE_SCHEDULE_ID,
		)
		return {"skipped": True, "reason": "disabled", "purged": 0}

	effective_batch = (
		batch_size if batch_size is not None else purge_settings.batch_size
	)
	cutoff = datetime.now(UTC) - timedelta(days=purge_settings.grace_period_days)
	async with async_session_local() as session:
		purged = await purge_expired_sessions(session, cutoff, effective_batch)
	logger.info(
		"user session purge completed purged=%d batch_size=%d cutoff=%s",
		purged,
		effective_batch,
		cutoff.isoformat(),
	)
	return {
		"purged": purged,
		"batch_size": effective_batch,
		"cutoff": cutoff.isoformat(),
	}


@broker.task(task_name=USER_SESSION_PURGE_TASK)
async def dispatch_user_session_purge() -> JSONObject:
	"""run the scheduled user session purge."""
	return await run_user_session_purge(respect_enabled=True)


async def reconcile_user_session_purge_schedule() -> bool:
	"""reconcile the user session purge schedule with current settings."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	await redis_schedule_source.delete_schedule(USER_SESSION_PURGE_SCHEDULE_ID)
	purge_settings = settings.tasks.user_session_purge
	if not purge_settings.enabled:
		logger.info("user session purge schedule cleared (disabled)")
		return False
	try:
		await (
			dispatch_user_session_purge.kicker()
			.with_schedule_id(USER_SESSION_PURGE_SCHEDULE_ID)
			.schedule_by_cron(redis_schedule_source, purge_settings.cron)
		)
	except ValueError as exc:
		logger.warning(
			"user session purge cron rejected by taskiq: %s (cron=%r)",
			exc,
			purge_settings.cron,
		)
		return False
	logger.info(
		"user session purge schedule installed cron=%r batch_size=%d grace_days=%d",
		purge_settings.cron,
		purge_settings.batch_size,
		purge_settings.grace_period_days,
	)
	return True


async def clear_disabled_user_session_purge_schedule() -> bool:
	"""remove a persisted purge schedule before startup when disabled."""
	if boot_settings.TESTING:
		return False
	settings.reload()
	if settings.tasks.user_session_purge.enabled:
		return False
	await redis_schedule_source.delete_schedule(USER_SESSION_PURGE_SCHEDULE_ID)
	logger.info(
		"user session purge schedule cleared before taskiq startup reason=disabled"
	)
	return True


on_settings_reload(reconcile_user_session_purge_schedule)
