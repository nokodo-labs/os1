"""TaskIQ broker and scheduler configuration."""

from __future__ import annotations

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import (
	ListQueueBroker,
	ListRedisScheduleSource,
	RedisAsyncResultBackend,
)

from api.settings import settings


_redis_settings = settings.cache.redis
_taskiq_settings = settings.tasks.taskiq


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


async def startup_taskiq() -> None:
	"""start the broker for API-side task publishing."""
	global _started
	if _started or broker.is_worker_process:
		return
	await broker.startup()
	_started = True


async def shutdown_taskiq() -> None:
	"""close the API-side broker connection."""
	global _started
	if not _started or broker.is_worker_process:
		return
	await broker.shutdown()
	_started = False
