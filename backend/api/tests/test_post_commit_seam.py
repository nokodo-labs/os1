"""post-commit actions belong to the commit that produced them.

the queue is the one seam repairable work goes through, so every owner of a
session has to drain it - not just request handlers. these tests pin the
contract: a session drains on close, a scope that owns its session drains, a
rollback drops only the work the rollback undid, and a site that rolls back and
KEEPS GOING must discard or its next commit runs the dead actions twice.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import post_commit
from api.database.main import async_session_local, session_scope
from api.database.post_commit import (
	PostCommitAction,
	discard_post_commit_actions,
	discard_uncommitted_post_commit_actions,
	enqueue_post_commit_action,
	pending_post_commit_action_count,
	run_post_commit_actions,
	run_post_commit_actions_safely,
)


def _recorder(ran: list[str]) -> Callable[[str], PostCommitAction]:
	"""build labelled actions that append to a shared list when they run."""

	def make(label: str) -> PostCommitAction:
		async def action(db: AsyncSession) -> None:
			_ = db
			ran.append(label)

		return action

	return make


@pytest.mark.asyncio
async def test_session_scope_drains_when_it_owns_the_session() -> None:
	"""background work is not a second, silently lossy seam."""
	ran: list[str] = []
	make = _recorder(ran)

	async with session_scope() as session:
		enqueue_post_commit_action(session, make("drained"))
		await session.commit()
		assert not ran, "must not run before the scope closes"

	assert ran == ["drained"]


@pytest.mark.asyncio
async def test_raw_session_drains_on_close() -> None:
	"""the contract: every app session drains on close, not just the wrappers."""
	ran: list[str] = []
	make = _recorder(ran)

	async with async_session_local() as session:
		enqueue_post_commit_action(session, make("drained"))
		await session.commit()
		assert not ran

	assert ran == ["drained"]


@pytest.mark.asyncio
async def test_uncommitted_actions_are_dropped_on_close() -> None:
	"""a session that never commits has nothing durable left to repair."""
	ran: list[str] = []
	make = _recorder(ran)

	async with async_session_local() as session:
		enqueue_post_commit_action(session, make("never-committed"))

	assert ran == []


@pytest.mark.asyncio
async def test_session_scope_does_not_drain_a_borrowed_session(
	db_session: AsyncSession,
) -> None:
	"""a borrowed session is drained by whoever owns it, not by the borrower."""
	ran: list[str] = []
	make = _recorder(ran)

	async with session_scope(db_session) as session:
		enqueue_post_commit_action(session, make("drained"))
		await session.commit()

	assert not ran
	assert pending_post_commit_action_count(db_session) == 1
	discard_post_commit_actions(db_session)


@pytest.mark.asyncio
async def test_rollback_keeps_actions_from_an_earlier_commit(
	db_session: AsyncSession,
) -> None:
	"""a mid-request commit's work survives a later rollback.

	the first action's work is durable, so its invalidation and fanout must
	still run; only the uncommitted tail goes away with the rollback.
	"""
	ran: list[str] = []
	make = _recorder(ran)

	enqueue_post_commit_action(db_session, make("committed"))
	await db_session.commit()

	enqueue_post_commit_action(db_session, make("rolled-back"))
	discard_uncommitted_post_commit_actions(db_session)
	await db_session.rollback()

	# the committed action is still owed a run; the rolled-back one is gone
	assert pending_post_commit_action_count(db_session) == 1

	await run_post_commit_actions(db_session)
	assert ran == ["committed"]


@pytest.mark.asyncio
async def test_rollback_and_retry_without_discard_runs_dead_actions_twice(
	db_session: AsyncSession,
) -> None:
	"""the leak close-time draining cannot see.

	a site that rolls back and KEEPS GOING in the same session leaves the failed
	attempt's actions queued, and the retry's commit promotes both sets. this
	pins the broken shape so the discard in the fixed shape below has a reason.
	"""
	ran: list[str] = []
	make = _recorder(ran)

	# failed attempt: enqueue, then roll back WITHOUT discarding
	enqueue_post_commit_action(db_session, make("attempt"))
	await db_session.rollback()

	# retry in the same session, then commit
	enqueue_post_commit_action(db_session, make("retry"))
	await db_session.commit()

	await run_post_commit_actions(db_session)
	assert ran == ["attempt", "retry"], "the dead attempt's action rode along"


@pytest.mark.asyncio
async def test_rollback_and_retry_with_discard_runs_only_the_retry(
	db_session: AsyncSession,
) -> None:
	"""the fixed shape: discard before a rollback that is followed by a retry."""
	ran: list[str] = []
	make = _recorder(ran)

	enqueue_post_commit_action(db_session, make("attempt"))
	discard_uncommitted_post_commit_actions(db_session)
	await db_session.rollback()

	enqueue_post_commit_action(db_session, make("retry"))
	await db_session.commit()

	await run_post_commit_actions(db_session)
	assert ran == ["retry"]


@pytest.mark.asyncio
async def test_bind_check_precedes_clearing_the_queue(
	db_session: AsyncSession,
	monkeypatch: MonkeyPatch,
) -> None:
	"""a session with no bind keeps its actions instead of losing them.

	the check used to run after ``committed.clear()``, so the raise took the
	actions with it and nothing could ever retry them.
	"""
	ran: list[str] = []
	make = _recorder(ran)

	enqueue_post_commit_action(db_session, make("kept"))
	await db_session.commit()

	monkeypatch.setattr(db_session, "bind", None)
	with pytest.raises(RuntimeError, match="no database bind"):
		await run_post_commit_actions(db_session)
	monkeypatch.undo()

	assert pending_post_commit_action_count(db_session) == 1
	await run_post_commit_actions(db_session)
	assert ran == ["kept"]


@pytest.mark.asyncio
async def test_safe_variant_swallows_non_group_failures(
	db_session: AsyncSession,
	monkeypatch: MonkeyPatch,
) -> None:
	"""the safe variant runs from ``close()``; it must never raise.

	it used to catch ``ExceptionGroup`` only, so the bind check above - and any
	other bare failure inside the runner - escaped session teardown.
	"""

	async def boom(session: AsyncSession) -> None:
		_ = session
		raise RuntimeError("not a group")

	monkeypatch.setattr(post_commit, "run_post_commit_actions", boom)
	await run_post_commit_actions_safely(db_session)


@pytest.mark.asyncio
async def test_failing_action_does_not_escape_close() -> None:
	"""an action that raises is logged, not propagated out of ``close()``."""

	async def boom(session: AsyncSession) -> None:
		_ = session
		raise RuntimeError("action exploded")

	async with async_session_local() as session:
		enqueue_post_commit_action(session, boom)
		await session.commit()
