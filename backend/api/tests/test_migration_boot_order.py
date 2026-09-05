"""a fresh boot on a stale store migrates before anything reads settings.

``api.settings`` reads ``settings_documents`` at IMPORT time and validates it
strictly, so a store holding a name a pending migration is meant to rewrite
would raise before the in-lifespan upgrade could run. the fix is the ordering:
``alembic upgrade`` runs in its own process (the ``migrate`` compose service,
gated on ``RUN_MIGRATIONS``), with everything that imports the app waiting on
it. these tests pin both halves against a real database - the rewrite really
happens, and the import-time read really succeeds afterwards.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.database.main as database_module
from api.boot_settings import boot_settings
from api.permissions import DefaultPermissions
from api.settings.database import _load_db_overrides
from api.settings.settings import Settings
from api.tests.conftest import _create_isolated_test_database_url, _drop_database


# the revision that rewrote three renamed and two removed permission names;
# "<rev>-1" is alembic's relative syntax for the revision just before it.
PERMISSIONS_REWRITE_REVISION = "9c1e4d7a8b23"
BEFORE_PERMISSIONS_REWRITE = f"{PERMISSIONS_REWRITE_REVISION}-1"

STALE_ACTION_PERMISSIONS = [
	"settings:write",  # renamed to settings:manage
	"roles:admin",  # renamed to roles:manage
	"files:upload",  # renamed to files:create
	"users:create",  # removed outright
	"threads:create",  # unchanged
]
MIGRATED_ACTION_PERMISSIONS = {
	"settings:manage",
	"roles:manage",
	"files:create",
	"threads:create",
}

SETTINGS_DOCUMENT_ID = "setdoc_00000000000000000000000000"


def _sync_url(url: URL) -> str:
	return url.set(drivername="postgresql+psycopg").render_as_string(
		hide_password=False
	)


def _alembic_config(url: URL) -> Config:
	config = database_module._build_alembic_config()
	config.set_main_option("sqlalchemy.url", _sync_url(url))
	return config


@pytest.fixture
def migration_database(
	monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[URL, Engine]]:
	"""an empty database plus a sync engine, dropped on the way out.

	``migrations/env.py`` rewrites ``sqlalchemy.url`` from ``boot_settings`` on
	every run, so aiming alembic at this database means aiming ``boot_settings``
	at it too - otherwise the upgrade would land on the real dev database.

	the provider is pointed away from qdrant for the same isolation reason the
	conftest pins ``:memory:``: one revision renames qdrant collections over
	HTTP as a side effect, and this test is about the schema and the settings
	rewrite, not about a vector store.
	"""
	url = _create_isolated_test_database_url()
	monkeypatch.setattr(boot_settings, "DATABASE_URL", _sync_url(url))
	monkeypatch.setenv("NOKODO__ASSETS__VECTOR_DATABASE__PROVIDER", "pgvector")
	engine = create_engine(_sync_url(url))
	try:
		yield url, engine
	finally:
		engine.dispose()
		_drop_database(url)


@pytest.fixture
def stale_store(migration_database: tuple[URL, Engine]) -> tuple[URL, Engine]:
	"""a database at the release before the rewrite, holding pre-rename names."""
	url, engine = migration_database
	command.upgrade(_alembic_config(url), BEFORE_PERMISSIONS_REWRITE)
	payload: dict[str, Any] = {"action_permissions": STALE_ACTION_PERMISSIONS}
	with engine.begin() as conn:
		conn.execute(
			text(
				"""
				INSERT INTO settings_documents
					(id, namespace, data, version, metadata, created_at, updated_at)
				VALUES (
					:id,
					'default_permissions',
					CAST(:data AS jsonb),
					1,
					'{}'::jsonb,
					NOW(),
					NOW()
				)
				"""
			),
			{"id": SETTINGS_DOCUMENT_ID, "data": json.dumps(payload)},
		)
	return url, engine


def _stored_permissions(engine: Engine) -> list[str]:
	with engine.connect() as conn:
		row = conn.execute(
			text(
				"SELECT data FROM settings_documents "
				"WHERE namespace = 'default_permissions'"
			)
		).one()
	data = row[0]
	assert isinstance(data, dict)
	permissions = data["action_permissions"]
	assert isinstance(permissions, list)
	return [str(value) for value in permissions]


def test_stale_store_would_break_an_unmigrated_boot(
	stale_store: tuple[URL, Engine],
) -> None:
	"""the premise: the pre-migration data is what the settings model rejects.

	without this the ordering the migrate service enforces would be arbitrary.
	"""
	_ = stale_store
	with pytest.raises(ValueError):
		DefaultPermissions.model_validate(
			{"action_permissions": STALE_ACTION_PERMISSIONS}
		)


def test_upgrade_rewrites_the_store_before_settings_read_it(
	stale_store: tuple[URL, Engine],
) -> None:
	"""the migrate step, in its own process: upgrade to head, then the read."""
	url, engine = stale_store

	command.upgrade(_alembic_config(url), "head")

	assert set(_stored_permissions(engine)) == MIGRATED_ACTION_PERMISSIONS
	loaded = DefaultPermissions.model_validate(
		{"action_permissions": _stored_permissions(engine)}
	)
	assert {str(value) for value in loaded.action_permissions} == (
		MIGRATED_ACTION_PERMISSIONS
	)


def test_import_time_settings_read_succeeds_after_migrating(
	stale_store: tuple[URL, Engine],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the real import-time read, not a stand-in.

	``_load_db_overrides`` is what ``DbSettingsSource`` calls while
	``api.settings`` is being imported - the read that must not see stale data.
	"""
	url, _engine = stale_store
	command.upgrade(_alembic_config(url), "head")

	async_engine = create_async_engine(_sync_url(url))
	monkeypatch.setattr(
		database_module,
		"_async_session_factory",
		async_sessionmaker(
			async_engine,
			class_=database_module.AppAsyncSession,
			expire_on_commit=False,
		),
	)
	# TESTING short-circuits the source; the point here is the real read
	monkeypatch.setattr(boot_settings, "TESTING", False)

	overrides = _load_db_overrides(Settings)

	section = overrides.get("default_permissions")
	assert section is not None
	assert set(section["action_permissions"]) == MIGRATED_ACTION_PERMISSIONS
