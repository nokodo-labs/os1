"""database configuration and session management."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from functools import partial
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from sqlalchemy.orm import Session, with_loader_criteria

from api.boot_settings import boot_settings
from api.database.post_commit import (
	discard_uncommitted_post_commit_actions,
	register_post_commit_promotion,
	run_post_commit_actions_safely,
)
from api.logging import get_logger
from api.models.mixins import SoftDeleteMixin


logger = get_logger(__name__)


class AppSession(Session):
	"""sync session backing every application session.

	its own class so the post-commit promotion listens here instead of on every
	`Session` in the process.
	"""


register_post_commit_promotion(AppSession)


_FLUSHED_KEY = "nokodo-ai:session:flushed"


@event.listens_for(AppSession, "after_flush")
def _mark_session_flushed(session: Session, flush_context: Any) -> None:
	_ = flush_context
	session.info[_FLUSHED_KEY] = True


@event.listens_for(AppSession, "after_commit")
@event.listens_for(AppSession, "after_rollback")
@event.listens_for(AppSession, "after_soft_rollback")
def _clear_session_flushed(session: Session, *args: Any) -> None:
	_ = args
	session.info.pop(_FLUSHED_KEY, None)


def has_uncommitted_writes(session: AsyncSession) -> bool:
	"""whether this session holds writes no other transaction can see yet.

	both halves matter. the identity map covers work not yet flushed; the
	flushed flag covers work already sent to the database inside the open
	transaction, which the identity map no longer reports and which a rollback
	will still undo. callers that PUBLISH a derived answer - to a cache, a
	search index, another process - must not do so from a session that returns
	True here, because the rows the answer was computed from may never land.
	"""
	sync_session = session.sync_session
	return bool(
		sync_session.new
		or sync_session.dirty
		or sync_session.deleted
		or sync_session.info.get(_FLUSHED_KEY)
	)


class AppAsyncSession(AsyncSession):
	"""application session that always drains its own post-commit actions.

	the queue is the one seam for repairable after-commit work, so it cannot
	depend on the owner remembering to drain: every session drains on close,
	whether it came from `get_db`, `session_scope`, or a raw
	`async_session_local()` in a task or background job. draining twice is a
	no-op, so the explicit drains in those wrappers stay as the fast path.

	work that was never committed is dropped here rather than run - a rollback
	already undid the rows it was meant to repair.
	"""

	sync_session_class = AppSession

	async def close(self) -> None:
		discard_uncommitted_post_commit_actions(self)
		await run_post_commit_actions_safely(self)
		await super().close()


# create async engine
engine = create_async_engine(
	boot_settings.DATABASE_URL,
	echo=boot_settings.DEBUG,
	future=True,
	pool_pre_ping=True,
	pool_size=boot_settings.DB_POOL_SIZE,
	max_overflow=boot_settings.DB_MAX_OVERFLOW,
	pool_timeout=boot_settings.DB_POOL_TIMEOUT,
	pool_recycle=boot_settings.DB_POOL_RECYCLE,
)

# accessed via async_session_local() so tests can swap the factory at
# runtime and consumers that imported the name still pick up the change.
_async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
	engine,
	class_=AppAsyncSession,
	expire_on_commit=False,
	autocommit=False,
	autoflush=False,
)


def async_session_local() -> AsyncSession:
	"""return a new async session from the current factory."""
	return _async_session_factory()


@contextlib.asynccontextmanager
async def session_scope(
	session: AsyncSession | None = None,
) -> AsyncGenerator[AsyncSession]:
	"""use the given session or create a fresh one.

	avoids the need for ``contextlib.AsyncExitStack`` when a function
	accepts an optional session and must fall back to a new one.

	a scope that OWNS its session drains post-commit actions exactly as
	``get_db`` does, so background work is not a second, silently lossy seam.
	a borrowed session is drained by whoever owns it.
	"""
	if session is not None:
		yield session
		return
	async with async_session_local() as new_session:
		try:
			try:
				yield new_session
			except Exception:
				discard_uncommitted_post_commit_actions(new_session)
				await new_session.rollback()
				raise
		finally:
			await run_post_commit_actions_safely(new_session)


async def safe_rollback(session: AsyncSession) -> None:
	"""rollback the session, swallowing errors if already closed."""
	discard_uncommitted_post_commit_actions(session)
	try:
		await session.rollback()
	except Exception:
		pass


@event.listens_for(Session, "do_orm_execute")
def _soft_delete_default_criteria(execute_state: Any) -> None:
	"""exclude soft-deleted rows by default for all SELECTs.

	to include them, use execution option include_deleted=True.
	"""
	if not execute_state.is_select:
		return
	if execute_state.execution_options.get("include_deleted"):
		return

	execute_state.statement = execute_state.statement.options(
		with_loader_criteria(
			SoftDeleteMixin,
			lambda cls: cls.deleted_at.is_(None),
			include_aliases=True,
			track_closure_variables=False,
		),
	)


async def get_db() -> AsyncGenerator[AsyncSession]:
	"""dependency for getting database sessions."""
	async with async_session_local() as session:
		try:
			try:
				yield session
				await session.commit()
			except Exception:
				# work committed earlier in the request keeps its actions; only
				# the uncommitted tail is dropped with the rollback.
				discard_uncommitted_post_commit_actions(session)
				await session.rollback()
				raise
		finally:
			try:
				await run_post_commit_actions_safely(session)
			finally:
				await session.close()


def _build_alembic_config() -> Config:
	"""return alembic config without relying on a .ini lookup."""
	script_location = Path(__file__).parent.parent / "migrations"
	config = Config()
	config.set_main_option("script_location", str(script_location))
	config.set_main_option("sqlalchemy.url", boot_settings.DATABASE_URL)
	return config


async def init_db() -> None:
	"""initialize database tables via alembic."""
	# mask credentials in url for logging
	db_url = boot_settings.DATABASE_URL
	if "@" in db_url:
		scheme_and_creds, host_and_db = db_url.rsplit("@", 1)
		scheme = scheme_and_creds.split("://")[0]
		safe_url = f"{scheme}://***@{host_and_db}"
	else:
		safe_url = db_url

	logger.info("initializing database", extra={"url": safe_url})

	migration_target = "heads" if boot_settings.BRANCHING_MIGRATIONS else "head"

	try:
		alembic_cfg = _build_alembic_config()
		loop = asyncio.get_running_loop()
		await loop.run_in_executor(
			None,
			partial(command.upgrade, alembic_cfg, migration_target),
		)
	except Exception as exc:
		logger.error("error running migrations: %s", exc)
		raise

	logger.info("database initialized")
