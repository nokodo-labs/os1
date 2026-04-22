"""redis / valkey client and primitives.

public surface (import EVERYTHING from ``api.redis`` directly - never
drill into the submodules from outside this package):

- ``redis_client`` / ``RedisClient`` - module-level singleton; access via
  ``redis_client.get()`` to obtain the underlying ``redis.asyncio.Redis``
  connection. ``connect()`` / ``aclose()`` are lifecycle hooks invoked
  from the FastAPI lifespan.
- ``PubSubChannel`` / ``make_run_channel`` - typed pub/sub helpers used by
  steering inbox + run sse fanout.
- ``cache`` / ``RedisCache`` - the keyed cache facade with tag invalidation.
- ``on_invalidation`` / ``publish_invalidation`` /
  ``start_invalidation_subscriber`` - cross-worker cache reset hooks.

design:

- single shared connection pool sized to the worker.
- explicit connect via ``connect()`` from lifespan; do NOT auto-connect
  on first use - we want startup failures to surface during boot.
- multi-worker primitives layer on top of this client:
  - ``api.v1.service.chat.steering`` - cross-worker steering inbox
  - ``api.v1.service.chat.run_bus`` - cross-worker SSE fanout
"""

from api.redis.cache import RedisCache, cache
from api.redis.cache_invalidation import (
	on_invalidation,
	publish_invalidation,
	start_invalidation_subscriber,
)
from api.redis.client import RedisClient, redis_client
from api.redis.pubsub import PubSubChannel, make_run_channel


__all__ = [
	"PubSubChannel",
	"RedisCache",
	"RedisClient",
	"cache",
	"make_run_channel",
	"on_invalidation",
	"publish_invalidation",
	"redis_client",
	"start_invalidation_subscriber",
]
