"""shared per-process runtime lifecycle for API and TaskIQ worker processes.

both process types run the same service layer with process-local caches and a
process-local settings snapshot, so both must connect the redis singleton,
configure storage backends, and subscribe to cross-process cache invalidation
signals. modules that own settings-derived state register a reset hook via
``on_settings_reload``; the ``settings`` invalidation signal reloads the
snapshot and then runs those hooks in every subscribed process.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from inspect import isawaitable

from api.redis import on_invalidation, redis_client, start_invalidation_subscriber
from api.settings import settings
from api.storage import close_all as close_storage
from api.storage import configure_storage_backends


logger = logging.getLogger(__name__)

SETTINGS_INVALIDATION_SIGNAL = "settings"

# hook results are ignored; awaitables are awaited before the next hook runs.
SettingsReloadHook = Callable[[], Awaitable[object] | object]

_settings_reload_hooks: list[SettingsReloadHook] = []
_invalidation_task: asyncio.Task[None] | None = None


def on_settings_reload(hook: SettingsReloadHook) -> None:
	"""register a hook to run after the settings snapshot reloads."""
	_settings_reload_hooks.append(hook)


async def apply_settings_change() -> None:
	"""reload the settings snapshot, then reset settings-derived runtime state."""
	await asyncio.to_thread(settings.reload)
	for hook in _settings_reload_hooks:
		try:
			result = hook()
			if isawaitable(result):
				await result
		except Exception:
			logger.exception("settings reload hook failed: %r", hook)


on_invalidation(SETTINGS_INVALIDATION_SIGNAL, apply_settings_change)
on_settings_reload(configure_storage_backends)


async def start_process_runtime() -> None:
	"""open the per-process dependencies shared by API and worker processes."""
	global _invalidation_task
	await redis_client.connect()
	await configure_storage_backends()
	if _invalidation_task is None or _invalidation_task.done():
		_invalidation_task = await start_invalidation_subscriber()


async def stop_process_runtime() -> None:
	"""close the per-process dependencies shared by API and worker processes."""
	global _invalidation_task
	if _invalidation_task is not None:
		_invalidation_task.cancel()
		with suppress(asyncio.CancelledError):
			await _invalidation_task
		_invalidation_task = None
	await close_storage()
	await redis_client.aclose()
