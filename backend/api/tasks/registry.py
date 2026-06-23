"""TaskIQ task registry bootstrap.

Worker and scheduler processes import this module once so concrete task modules
can register runners and schedules with the shared broker. keep this bootstrap
version-neutral; versioned APIs can contribute tasks through imported registries.
"""

from api.v1.tasks import registry as _v1_registry


__all__: list[str] = []

_ = (_v1_registry,)
