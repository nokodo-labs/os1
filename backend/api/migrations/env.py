"""Alembic environment configuration."""

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from api import models  # noqa: F401
from api.core.config import configure_psycopg_asyncio_event_loop_policy, settings
from api.models.base import Base


configure_psycopg_asyncio_event_loop_policy()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
	fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Override sqlalchemy.url with the one from settings
config.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))


def run_migrations_offline() -> None:
	"""Run migrations in 'offline' mode.

	This configures the context with just a URL
	and not an Engine, though an Engine is acceptable
	here as well.  By skipping the Engine creation
	we don't even need a DBAPI to be available.

	Calls to context.execute() here emit the given string to the
	script output.
	"""
	url = config.get_main_option("sqlalchemy.url")
	context.configure(
		url=url,
		target_metadata=target_metadata,
		literal_binds=True,
		dialect_opts={"paramstyle": "named"},
		render_as_batch=True,
	)

	with context.begin_transaction():
		context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
	"""Run migrations with the given connection."""
	context.configure(
		connection=connection,
		target_metadata=target_metadata,
		render_as_batch=True,
	)

	with context.begin_transaction():
		context.run_migrations()


async def run_async_migrations() -> None:
	"""Run migrations in 'online' mode with async engine."""
	connectable = async_engine_from_config(
		config.get_section(config.config_ini_section, {}),
		prefix="sqlalchemy.",
		poolclass=pool.NullPool,
	)

	async with connectable.connect() as connection:
		await connection.run_sync(do_run_migrations)

	await connectable.dispose()


def run_migrations_online() -> None:
	"""Run migrations in 'online' mode."""
	asyncio.run(run_async_migrations())


if context.is_offline_mode():
	run_migrations_offline()
else:
	run_migrations_online()
