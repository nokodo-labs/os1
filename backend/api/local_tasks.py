"""shared in-process background task utilities.

centralizes fire-and-forget asyncio task management. all local background
tasks in the application should use create_background_task() so that:

1. strong references are kept (prevents GC in python 3.13+)
2. exceptions are always logged

TaskIQ execution is explicit and lives in durable task modules. arbitrary
coroutine helpers stay local because they are not serializable worker jobs.
"""

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
	"""create and track an in-process asyncio background task.

	always local: the task shares this process's state (the run status store,
	SSE producers its own subscribers consume) and never reaches a remote
	worker, which is what makes it safe for work a TaskIQ job could not do.

	the task is held by a module-level strong reference set so it will not be
	garbage-collected before completion. exceptions are logged automatically
	via a done callback.

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


async def drain_background_tasks(
	name_prefix: str | None = None,
	timeout: float = 30.0,
) -> None:
	"""wait for in-flight background tasks to finish.

	fire-and-forget work still has to land before a process stops accepting
	it, so shutdown (and anything else that must observe the result) waits
	here rather than assuming the loop got around to it.
	"""
	deadline = asyncio.get_running_loop().time() + timeout
	while True:
		pending = {
			task
			for task in _background_tasks
			if name_prefix is None or (task.get_name() or "").startswith(name_prefix)
		}
		if not pending:
			return
		remaining = deadline - asyncio.get_running_loop().time()
		if remaining <= 0:
			logger.warning(
				"background tasks still running after %ss: %s",
				timeout,
				sorted(task.get_name() for task in pending),
			)
			return
		await asyncio.wait(pending, timeout=remaining)


def _on_task_done(task: asyncio.Task[object], name: str) -> None:
	"""done callback - discard reference and log failures."""
	_background_tasks.discard(task)
	if task.cancelled():
		return
	exc = task.exception()
	if exc is not None:
		logger.exception("background task failed: %s", name, exc_info=exc)
