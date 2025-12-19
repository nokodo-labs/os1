"""Database configuration and session management."""

import asyncio
import sys
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

from api.core.config import settings
from api.core.logging import get_logger
from api.models.mixins import SoftDeleteMixin


logger = get_logger(__name__)


def _configure_psycopg_asyncio_event_loop_policy() -> None:
	"""Ensure psycopg runs on a selector event loop on Windows."""
	# psycopg async mode is not compatible with Windows' default Proactor event loop.
	if sys.platform == "win32":
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


_configure_psycopg_asyncio_event_loop_policy()


# Create async engine
engine = create_async_engine(
	str(settings.DATABASE_URL),
	echo=settings.DEBUG,
	future=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
	engine,
	class_=AsyncSession,
	expire_on_commit=False,
	autocommit=False,
	autoflush=False,
)


@event.listens_for(Session, "do_orm_execute")
def _soft_delete_default_criteria(execute_state: Any) -> None:
	"""Exclude soft-deleted rows by default for all SELECTs.

	To include them, use execution option include_deleted=True.
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
	"""Dependency for getting database sessions."""
	async with AsyncSessionLocal() as session:
		try:
			yield session
			await session.commit()
		except Exception:
			await session.rollback()
			raise
		finally:
			await session.close()


def _build_alembic_config() -> Config:
	"""return alembic config without relying on a .ini lookup."""
	script_location = Path(__file__).parent.parent / "migrations"
	config = Config()
	config.set_main_option("script_location", str(script_location))
	config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))
	return config


async def init_db() -> None:
	"""initialize database tables via alembic."""
	# mask credentials in url for logging
	db_url = str(settings.DATABASE_URL)
	if "@" in db_url:
		scheme_and_creds, host_and_db = db_url.rsplit("@", 1)
		scheme = scheme_and_creds.split("://")[0]
		safe_url = f"{scheme}://***@{host_and_db}"
	else:
		safe_url = db_url

	logger.info("initializing database", extra={"url": safe_url})

	try:
		alembic_cfg = _build_alembic_config()
		loop = asyncio.get_running_loop()
		await loop.run_in_executor(
			None,
			partial(command.upgrade, alembic_cfg, "head"),
		)
	except Exception as exc:
		logger.error(f"error running migrations: {exc}")
		raise

	logger.info("database initialized")
