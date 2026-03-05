"""shared background task utilities.

centralizes fire-and-forget asyncio task management. all background
tasks in the application should use create_background_task() so that:

1. strong references are kept (prevents GC in python 3.13+)
2. exceptions are always logged
3. when TaskIQ is adopted, this is the single swap point
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine


logger = logging.getLogger(__name__)

# strong references to background tasks so the event loop does not GC them.
# python 3.12+ only keeps weak references from asyncio.create_task().
_background_tasks: set[asyncio.Task[object]] = set()


def create_background_task[T](
	coro: Coroutine[object, object, T],
	*,
	name: str,
) -> asyncio.Task[T]:
	"""create and track an asyncio background task.

	the task is held by a module-level strong reference set so it
	will not be garbage-collected before completion. exceptions are
	logged automatically via a done callback.

	args:
		coro: the coroutine to schedule.
		name: human-readable label for log messages.

	returns:
		the created asyncio.Task.
	"""
	task = asyncio.create_task(coro, name=name)
	_background_tasks.add(task)
	task.add_done_callback(lambda t: _on_task_done(t, name))
	return task


def _on_task_done(task: asyncio.Task[object], name: str) -> None:
	"""done callback - discard reference and log failures."""
	_background_tasks.discard(task)
	if task.cancelled():
		return
	exc = task.exception()
	if exc is not None:
		logger.exception("background task failed: %s", name, exc_info=exc)
