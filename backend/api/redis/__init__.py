"""redis / valkey client and primitives.

public surface (import EVERYTHING from ``api.redis`` directly - never
drill into the submodules from outside this package):

- ``redis_client`` / ``RedisClient`` - module-level singleton; access via
	``redis_client.get()`` to obtain the underlying ``redis.asyncio.Redis``
	connection. ``connect()`` / ``aclose()`` are lifecycle hooks invoked
	from the FastAPI lifespan and TaskIQ worker startup/shutdown.
- ``PubSubChannel`` / ``make_run_channel`` / ``make_task_channel`` - typed
	pub/sub helpers used by SSE fanout and event fanout.
- ``SseFrameBus`` - mirror + replay a stream of SSE frames across workers
	(catchup log + live pub/sub). configured per resource kind by its owner.
- ``cache`` / ``RedisCache`` - the keyed cache facade with tag invalidation.
- ``on_invalidation`` / ``publish_invalidation`` /
  ``start_invalidation_subscriber`` - cross-worker cache reset hooks.

design:

- single shared connection pool sized to the worker.
- explicit connect via ``connect()`` from process lifecycle hooks; do NOT
	auto-connect on first use - we want startup failures to surface during boot.
- multi-worker primitives layer on top of this client:
	- ``api.v1.service.runs.bus`` - cross-worker run SSE fanout
	- ``api.v1.service.tasks`` - cross-worker task SSE fanout
	- ``api.v1.service.event_bus`` - cross-worker websocket event fanout
"""

from api.redis.cache import RedisCache, cache
from api.redis.cache_invalidation import (
	on_invalidation,
	publish_invalidation,
	start_invalidation_subscriber,
)
from api.redis.client import RedisClient, redis_client
from api.redis.pubsub import PubSubChannel, make_run_channel, make_task_channel
from api.redis.sse_bus import SseFrameBus


__all__ = [
	"PubSubChannel",
	"RedisCache",
	"RedisClient",
	"SseFrameBus",
	"cache",
	"make_run_channel",
	"make_task_channel",
	"on_invalidation",
	"publish_invalidation",
	"redis_client",
	"start_invalidation_subscriber",
]
