"""repairable async actions that run only after a session commit.

enqueue only work whose loss is repaired from durable state, such as committed
event rows, cache TTLs, or staleness scans. permanently lossy work does not
belong in this queue. actions run on a fresh read-only session and cannot enqueue
more actions.

an action belongs to the commit that produced it, not to the request that
enqueued it: the session's ``after_commit`` event promotes queued actions to a
committed list, and only uncommitted actions are dropped by a later rollback.

contract: every app session drains on close. ``AppAsyncSession.close`` discards
uncommitted actions and runs committed ones, so no owner of a session - request
handler, task, or background job - has to remember to drain. draining twice is a
no-op, so the explicit drains in ``get_db`` and ``session_scope`` stay as the
fast path.

the one thing close-time draining cannot see is a session that rolls back and
KEEPS GOING: its already-queued actions outlive the rollback in the same
session, and the retry's commit would promote and run them a second time. a site
that rolls back and continues must discard explicitly - use
``discard_uncommitted_post_commit_actions`` when earlier commits in the same
session are still owed their run, or ``discard_post_commit_actions`` to drop
everything. a site that rolls back and RAISES needs nothing: close-time discard
handles it.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from weakref import finalize

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


type PostCommitAction = Callable[[AsyncSession], Awaitable[None]]


logger = logging.getLogger(__name__)
_QUEUE_KEY = "nokodo-ai:post-commit:queue"
_DRAINING_KEY = "nokodo-ai:post-commit:draining"


@dataclass(slots=True)
class _QueueState:
	pending: int = 0


@dataclass(slots=True)
class _PostCommitQueue:
	actions: list[PostCommitAction] = field(default_factory=list)
	committed: list[PostCommitAction] = field(default_factory=list)
	state: _QueueState = field(default_factory=_QueueState)

	def refresh_pending(self) -> None:
		self.state.pending = len(self.actions) + len(self.committed)


def _warn_abandoned_queue(state: _QueueState) -> None:
	if state.pending:
		logger.error(
			"database session was garbage-collected with %d pending "
			"post-commit actions",
			state.pending,
		)


def _queue(session: AsyncSession, create: bool) -> _PostCommitQueue | None:
	queue = session.info.get(_QUEUE_KEY)
	if isinstance(queue, _PostCommitQueue):
		return queue
	if not create:
		return None
	queue = _PostCommitQueue()
	session.info[_QUEUE_KEY] = queue
	finalize(session, _warn_abandoned_queue, queue.state)
	return queue


def _promote_committed_actions(session: Session) -> None:
	"""bind queued actions to the commit that produced them."""
	queue = session.info.get(_QUEUE_KEY)
	if not isinstance(queue, _PostCommitQueue) or not queue.actions:
		return
	queue.committed.extend(queue.actions)
	queue.actions.clear()
	queue.refresh_pending()


def register_post_commit_promotion(session_class: type[Session]) -> None:
	"""listen for commits on one session class.

	scoped rather than global: every `Session` in the process would include
	sessions this queue knows nothing about.
	"""
	event.listen(session_class, "after_commit", _promote_committed_actions)


def enqueue_post_commit_action(
	session: AsyncSession,
	action: PostCommitAction,
) -> None:
	"""enqueue an async action for the session's next successful commit."""
	if session.info.get(_DRAINING_KEY) is True:
		raise RuntimeError("post-commit actions cannot enqueue more actions")
	queue = _queue(session, True)
	if queue is None:
		raise RuntimeError("failed to create post-commit queue")
	queue.actions.append(action)
	queue.refresh_pending()


async def run_post_commit_actions(session: AsyncSession) -> None:
	"""run and clear actions bound to this session's completed commits."""
	queue = _queue(session, False)
	if queue is None:
		return
	bind = session.bind
	if bind is None:
		raise RuntimeError("post-commit action session has no database bind")
	actions = list(queue.committed)
	queue.committed.clear()
	queue.refresh_pending()
	if not actions:
		return
	errors: list[Exception] = []
	async with AsyncSession(bind=bind, expire_on_commit=False, autoflush=False) as db:
		db.info[_DRAINING_KEY] = True
		for action in actions:
			try:
				await action(db)
			except Exception as exc:
				errors.append(exc)
			finally:
				await db.rollback()
	if errors:
		raise ExceptionGroup("post-commit actions failed", errors)


async def run_post_commit_actions_safely(session: AsyncSession) -> None:
	"""run post-commit actions and log any failure without raising.

	catches every exception, not just the aggregate one: this runs from
	``AppAsyncSession.close``, where raising would turn a repairable drain
	failure into a broken session teardown.
	"""
	try:
		await run_post_commit_actions(session)
	except Exception:
		logger.exception("post-commit actions failed after a successful commit")


def discard_uncommitted_post_commit_actions(session: AsyncSession) -> None:
	"""discard actions whose work a rollback is about to undo.

	actions already bound to an earlier successful commit survive: their work is
	committed, so their invalidation and fanout must still run.
	"""
	queue = _queue(session, False)
	if queue is not None:
		queue.actions.clear()
		queue.refresh_pending()


def discard_post_commit_actions(session: AsyncSession) -> None:
	"""discard every action queued on a session, committed or not."""
	queue = _queue(session, False)
	if queue is not None:
		queue.actions.clear()
		queue.committed.clear()
		queue.refresh_pending()


def pending_post_commit_action_count(session: AsyncSession) -> int:
	"""return actions still owed a run: queued, plus committed-but-undrained.

	the committed half is the one worth shouting about at close time - that work
	is durable and its invalidation or fanout never ran.
	"""
	queue = _queue(session, False)
	if queue is None:
		return 0
	return len(queue.actions) + len(queue.committed)
