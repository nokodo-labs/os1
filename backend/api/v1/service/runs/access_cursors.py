"""access revision cursors scoped to active local runs."""

from api.database import async_session_local
from api.permissions import ResourceType
from api.v1.service.authorization import current_access_revision
from api.v1.service.runs.status import run_registry
from nokodo_ai.utils.typeid import TypeID


_cursors: dict[TypeID, int] = {}
"""access revision each thread's local runs have been reconciled through.

only threads this process is currently running: a cursor outlives no run, so
the map stays the size of the local workload.
"""


async def initialize_thread_access_cursor(thread_id: TypeID) -> None:
	"""seed a cursor when a process gains its first local run for a thread."""
	if thread_id in _cursors:
		return
	async with async_session_local() as session:
		_cursors[thread_id] = await current_access_revision(
			(ResourceType.THREAD, thread_id),
			session,
		)


async def release_thread_access_cursor(thread_id: TypeID | None) -> None:
	"""drop a cursor after the process loses its last local thread run."""
	if thread_id is None or await run_registry.local_run_ids(thread_id):
		return
	_cursors.pop(thread_id, None)


def access_revision_cursor(thread_id: TypeID) -> int:
	"""return the process cursor for one thread."""
	return _cursors.get(thread_id, 0)


def set_access_revision_cursor(thread_id: TypeID, revision: int) -> None:
	"""advance the process cursor for one thread."""
	_cursors[thread_id] = revision


def drop_access_revision_cursor(thread_id: TypeID) -> None:
	"""drop one thread cursor immediately."""
	_cursors.pop(thread_id, None)
