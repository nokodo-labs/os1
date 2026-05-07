"""TaskIQ broker, scheduler, CLI shim, and process lifecycle hooks.

the API process uses ``startup_taskiq`` only as a publisher. worker and
scheduler processes run this module with ``python -m api.taskiq ...`` so the
Windows selector-loop policy is applied before TaskIQ creates event loops.

worker startup connects the process-local Redis singleton because task runners
use the same service layer as the API. worker/scheduler startup handlers also
write short-lived Redis status keys. the API monitor logs a critical error when
either role first goes missing, because durable tasks have no in-process fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
from contextlib import suppress
from datetime import UTC, datetime
from typing import Literal

import redis.asyncio as redis_async
from redis.asyncio import Redis
from redis.exceptions import RedisError
from taskiq import TaskiqScheduler
from taskiq.events import TaskiqEvents
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import (
	ListQueueBroker,
	ListRedisScheduleSource,
	RedisAsyncResultBackend,
)

from api.redis import redis_client
from api.runtime import configure_psycopg_asyncio_event_loop_policy
from api.settings import settings


configure_psycopg_asyncio_event_loop_policy()

logger = logging.getLogger(__name__)

_redis_settings = settings.cache.redis
_taskiq_settings = settings.tasks.taskiq

type TaskiqProcessRole = Literal["worker", "scheduler"]

_STATUS_KEY_PREFIX = "nokodo-ai:taskiq:status"
_STATUS_TTL_SECONDS = 45
_STATUS_HEARTBEAT_SECONDS = 15
_STATUS_MONITOR_SECONDS = 30
_REQUIRED_PROCESS_STARTUP_TIMEOUT_SECONDS = 30.0
_REQUIRED_PROCESS_STARTUP_POLL_SECONDS = 0.5
_REQUIRED_PROCESS_ROLES: tuple[TaskiqProcessRole, ...] = ("worker", "scheduler")
_PROCESS_ID = f"{socket.gethostname()}:{os.getpid()}"

_monitor_task: asyncio.Task[None] | None = None
_worker_status_task: asyncio.Task[None] | None = None
_scheduler_status_task: asyncio.Task[None] | None = None
_worker_status_redis: Redis | None = None
_scheduler_status_redis: Redis | None = None


result_backend: RedisAsyncResultBackend[object] = RedisAsyncResultBackend(
	redis_url=_redis_settings.url,
	result_ex_time=_taskiq_settings.result_ttl_seconds,
	max_connection_pool_size=_taskiq_settings.max_connections,
)

broker = ListQueueBroker(
	url=_redis_settings.url,
	queue_name=_taskiq_settings.queue_name,
	max_connection_pool_size=_taskiq_settings.max_connections,
).with_result_backend(result_backend)

redis_schedule_source = ListRedisScheduleSource(
	_redis_settings.url,
	prefix=_taskiq_settings.schedule_prefix,
	max_connection_pool_size=_taskiq_settings.max_connections,
)

scheduler = TaskiqScheduler(
	broker=broker,
	sources=[
		LabelScheduleSource(broker),
		redis_schedule_source,
	],
)

_started = False


def _redacted_redis_url() -> str:
	"""return the Redis URL with credentials removed for logs."""
	url = _redis_settings.url
	if "@" not in url:
		return url
	prefix, suffix = url.rsplit("@", 1)
	scheme = prefix.split(":", 1)[0]
	return f"{scheme}://***@{suffix}"


def _status_key(role: TaskiqProcessRole) -> str:
	"""build the Redis heartbeat key for this process and role."""
	return f"{_STATUS_KEY_PREFIX}:{role}:{_PROCESS_ID}"


def _status_payload(role: TaskiqProcessRole, status_value: str) -> dict[str, object]:
	"""build the JSON payload stored in a TaskIQ process heartbeat."""
	return {
		"role": role,
		"status": status_value,
		"host": socket.gethostname(),
		"pid": os.getpid(),
		"queue": _taskiq_settings.queue_name,
		"schedule_prefix": _taskiq_settings.schedule_prefix,
		"updated_at": datetime.now(tz=UTC).isoformat(),
	}


def _status_redis_client(role: TaskiqProcessRole) -> Redis:
	"""create a small dedicated Redis client for process heartbeats."""
	return redis_async.from_url(
		_redis_settings.url,
		max_connections=2,
		socket_timeout=2.0,
		socket_connect_timeout=2.0,
		decode_responses=False,
		client_name=f"{_redis_settings.client_name}:taskiq-{role}",
	)


async def _write_process_status(
	conn: Redis,
	role: TaskiqProcessRole,
	status_value: str,
) -> None:
	"""write one heartbeat payload with a TTL."""
	payload = json.dumps(_status_payload(role, status_value)).encode("utf-8")
	await conn.set(_status_key(role), payload, ex=_STATUS_TTL_SECONDS)


async def _process_status_loop(
	role: TaskiqProcessRole,
	conn: Redis,
) -> None:
	"""refresh the current process heartbeat until shutdown."""
	logger.info(
		"taskiq %s heartbeat started pid=%s host=%s queue=%s prefix=%s redis=%s",
		role,
		os.getpid(),
		socket.gethostname(),
		_taskiq_settings.queue_name,
		_taskiq_settings.schedule_prefix,
		_redacted_redis_url(),
	)
	while True:
		try:
			await _write_process_status(conn, role, "running")
		except (RedisError, OSError) as exc:
			logger.warning("taskiq %s heartbeat failed: %s", role, exc)
		await asyncio.sleep(_STATUS_HEARTBEAT_SECONDS)


async def _start_process_status(role: TaskiqProcessRole) -> None:
	"""start heartbeat state for a TaskIQ worker or scheduler process."""
	global _scheduler_status_redis, _scheduler_status_task
	global _worker_status_redis, _worker_status_task

	current_task = _worker_status_task if role == "worker" else _scheduler_status_task
	if current_task is not None and not current_task.done():
		return

	conn = _status_redis_client(role)
	try:
		ping_result = conn.ping()
		if not isinstance(ping_result, bool):
			await ping_result
		await _write_process_status(conn, role, "running")
	except Exception:
		await conn.aclose()
		raise
	task = asyncio.create_task(
		_process_status_loop(role, conn),
		name=f"taskiq-{role}-heartbeat",
	)
	if role == "worker":
		_worker_status_redis = conn
		_worker_status_task = task
	else:
		_scheduler_status_redis = conn
		_scheduler_status_task = task


async def _stop_process_status(role: TaskiqProcessRole) -> None:
	"""stop heartbeat state and remove the process status key."""
	global _scheduler_status_redis, _scheduler_status_task
	global _worker_status_redis, _worker_status_task

	current_task = _worker_status_task if role == "worker" else _scheduler_status_task
	conn = _worker_status_redis if role == "worker" else _scheduler_status_redis
	if current_task is not None:
		current_task.cancel()
		with suppress(asyncio.CancelledError):
			await current_task
	if conn is not None:
		with suppress(RedisError, OSError):
			await _write_process_status(conn, role, "stopped")
			await conn.delete(_status_key(role))
		await conn.aclose()
	if role == "worker":
		_worker_status_redis = None
		_worker_status_task = None
	else:
		_scheduler_status_redis = None
		_scheduler_status_task = None
	logger.info("taskiq %s heartbeat stopped pid=%s", role, os.getpid())


async def _count_process_statuses(role: TaskiqProcessRole) -> int:
	"""count live heartbeat keys for one TaskIQ process role."""
	conn = redis_client.get()
	count = 0
	async for _key in conn.scan_iter(match=f"{_STATUS_KEY_PREFIX}:{role}:*"):
		count += 1
	return count


async def _process_status_counts() -> dict[TaskiqProcessRole, int]:
	"""return live heartbeat counts for all required TaskIQ roles."""
	return {
		"worker": await _count_process_statuses("worker"),
		"scheduler": await _count_process_statuses("scheduler"),
	}


def _missing_process_roles(
	counts: dict[TaskiqProcessRole, int],
) -> tuple[TaskiqProcessRole, ...]:
	"""return required TaskIQ roles without a live heartbeat."""
	return tuple(role for role in _REQUIRED_PROCESS_ROLES if counts.get(role, 0) < 1)


def _missing_process_error(
	missing_roles: tuple[TaskiqProcessRole, ...],
) -> RuntimeError:
	"""build the fatal startup error for missing TaskIQ roles."""
	missing_value = ", ".join(missing_roles)
	return RuntimeError(f"required taskiq processes are missing: {missing_value}")


def _log_missing_taskiq_processes(
	counts: dict[TaskiqProcessRole, int],
	reason: str,
) -> None:
	"""log one critical missing-process event."""
	logger.critical(
		"taskiq required processes missing workers=%s schedulers=%s "
		"queue=%s prefix=%s; %s",
		counts.get("worker", 0),
		counts.get("scheduler", 0),
		_taskiq_settings.queue_name,
		_taskiq_settings.schedule_prefix,
		reason,
	)


async def _wait_for_required_taskiq_processes(timeout_seconds: float) -> None:
	"""wait for required worker and scheduler heartbeats during API startup."""
	loop = asyncio.get_running_loop()
	deadline = loop.time() + timeout_seconds
	while True:
		try:
			counts = await _process_status_counts()
		except (RedisError, OSError) as exc:
			logger.critical(
				"taskiq required process check failed during api startup: %s",
				exc,
			)
			raise RuntimeError(
				"required taskiq process check failed during api startup"
			) from exc
		missing_roles = _missing_process_roles(counts)
		if not missing_roles:
			return
		if loop.time() >= deadline:
			_log_missing_taskiq_processes(counts, "api startup aborted")
			raise _missing_process_error(missing_roles)
		await asyncio.sleep(
			min(_REQUIRED_PROCESS_STARTUP_POLL_SECONDS, deadline - loop.time())
		)


def _log_required_process_status_change(
	counts: dict[TaskiqProcessRole, int],
	previous_missing_roles: tuple[TaskiqProcessRole, ...],
) -> tuple[TaskiqProcessRole, ...]:
	"""log only TaskIQ required-process status transitions."""
	missing_roles = _missing_process_roles(counts)
	if missing_roles:
		if missing_roles != previous_missing_roles:
			_log_missing_taskiq_processes(counts, "durable tasks have no fallback")
		return missing_roles
	if previous_missing_roles:
		logger.info(
			"taskiq required processes recovered workers=%s schedulers=%s "
			"queue=%s prefix=%s",
			counts.get("worker", 0),
			counts.get("scheduler", 0),
			_taskiq_settings.queue_name,
			_taskiq_settings.schedule_prefix,
		)
	return ()


async def _monitor_taskiq_processes() -> None:
	"""watch required TaskIQ roles and log only status transitions."""
	previous_missing_roles: tuple[TaskiqProcessRole, ...] = ()
	while True:
		try:
			counts = await _process_status_counts()
		except (RedisError, OSError) as exc:
			if previous_missing_roles != _REQUIRED_PROCESS_ROLES:
				logger.critical("taskiq required process check failed: %s", exc)
			previous_missing_roles = _REQUIRED_PROCESS_ROLES
		else:
			previous_missing_roles = _log_required_process_status_change(
				counts,
				previous_missing_roles,
			)
		await asyncio.sleep(_STATUS_MONITOR_SECONDS)


async def _start_worker_process_dependencies() -> None:
	"""open dependencies used by task runners in a worker process."""
	try:
		await redis_client.connect()
		await _start_process_status("worker")
	except Exception as exc:
		logger.critical("taskiq worker startup failed: %s", exc, exc_info=True)
		with suppress(Exception):
			await _stop_process_status("worker")
		with suppress(Exception):
			await redis_client.aclose()
		raise


async def _stop_worker_process_dependencies() -> None:
	"""close dependencies used by task runners in a worker process."""
	await _stop_process_status("worker")
	await redis_client.aclose()


async def _start_scheduler_process_dependencies() -> None:
	"""open dependencies used by the scheduler process."""
	try:
		await _start_process_status("scheduler")
	except Exception as exc:
		logger.critical("taskiq scheduler startup failed: %s", exc, exc_info=True)
		with suppress(Exception):
			await _stop_process_status("scheduler")
		raise


async def _stop_scheduler_process_dependencies() -> None:
	"""close dependencies used by the scheduler process."""
	await _stop_process_status("scheduler")


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _taskiq_worker_startup(_state: object) -> None:
	"""open worker dependencies and publish presence once TaskIQ accepts jobs."""
	await _start_worker_process_dependencies()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _taskiq_worker_shutdown(_state: object) -> None:
	"""close worker dependencies on graceful shutdown."""
	await _stop_worker_process_dependencies()


@broker.on_event(TaskiqEvents.CLIENT_STARTUP)
async def _taskiq_client_startup(_state: object) -> None:
	"""publish scheduler presence when the client startup is the scheduler."""
	if broker.is_scheduler_process:
		await _start_scheduler_process_dependencies()


@broker.on_event(TaskiqEvents.CLIENT_SHUTDOWN)
async def _taskiq_client_shutdown(_state: object) -> None:
	"""remove scheduler presence on graceful shutdown."""
	if broker.is_scheduler_process:
		await _stop_scheduler_process_dependencies()


async def startup_taskiq() -> None:
	"""start the broker for API-side task publishing."""
	global _monitor_task, _started
	if _started or broker.is_worker_process:
		return
	logger.info(
		"starting taskiq api publisher queue=%s prefix=%s redis=%s",
		_taskiq_settings.queue_name,
		_taskiq_settings.schedule_prefix,
		_redacted_redis_url(),
	)
	try:
		await broker.startup()
	except Exception as exc:
		logger.critical("taskiq api publisher startup failed: %s", exc, exc_info=True)
		raise
	_started = True
	try:
		await _wait_for_required_taskiq_processes(
			_REQUIRED_PROCESS_STARTUP_TIMEOUT_SECONDS
		)
	except Exception:
		with suppress(Exception):
			await broker.shutdown()
		_started = False
		raise
	logger.info("taskiq api publisher connected queue=%s", _taskiq_settings.queue_name)
	if _monitor_task is None or _monitor_task.done():
		_monitor_task = asyncio.create_task(
			_monitor_taskiq_processes(),
			name="taskiq-process-monitor",
		)


async def shutdown_taskiq() -> None:
	"""close the API-side broker connection."""
	global _monitor_task, _started
	if not _started or broker.is_worker_process:
		return
	if _monitor_task is not None:
		_monitor_task.cancel()
		with suppress(asyncio.CancelledError):
			await _monitor_task
		_monitor_task = None
	await broker.shutdown()
	_started = False
	logger.info(
		"taskiq api publisher disconnected queue=%s", _taskiq_settings.queue_name
	)


def main() -> None:
	"""run the TaskIQ CLI with the backend runtime policy applied first."""
	configure_psycopg_asyncio_event_loop_policy()
	sys.modules.setdefault("api.taskiq", sys.modules[__name__])
	from taskiq.__main__ import main as taskiq_main

	taskiq_main()


if __name__ == "__main__":
	main()
