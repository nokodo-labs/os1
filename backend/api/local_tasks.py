"""shared in-process background task utilities.

centralizes fire-and-forget asyncio task management. all local background
tasks in the application should use create_background_task() so that:

1. strong references are kept (prevents GC in python 3.13+)
2. exceptions are always logged

TaskIQ execution is explicit and lives in durable task modules. arbitrary
coroutine helpers stay local because they are not serializable worker jobs.
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
	return _spawn_local(coro, name=name)


def create_inline_background_task[T](
	coro: Coroutine[object, object, T],
	name: str,
) -> asyncio.Task[T]:
	"""create an in-process background task that is guaranteed never to be
	routed to a remote worker.

	use this for work that must share in-process state with the caller
	(e.g. publishing into the local run_status_store, driving SSE producers
	that subscribers in the same process consume) or that must stay snappy
	(no broker hop, no serialization).

	args:
		coro: the coroutine to schedule.
		name: human-readable label for log messages.

	returns:
		the created asyncio.Task.
	"""
	return _spawn_local(coro, name=name)


def _spawn_local[T](
	coro: Coroutine[object, object, T],
	name: str,
) -> asyncio.Task[T]:
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
