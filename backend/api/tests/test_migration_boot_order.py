"""a fresh boot on a stale store migrates before anything reads settings.

``api.settings`` reads ``settings_documents`` at IMPORT time and validates it
strictly, so a store holding a name a pending migration is meant to rewrite
would raise before the in-lifespan upgrade could run. the fix is the ordering:
``alembic upgrade`` runs in its own process (the ``migrate`` compose service,
gated on ``RUN_MIGRATIONS``), with everything that imports the app waiting on
it.

both halves are pinned here. the DATA half runs against a real database - the
rewrite really happens, and the import-time read really succeeds afterwards.
the ORDERING half is static: the compose services declare the gate, the
entrypoint declares the trigger, and - the load-bearing premise nothing else
would catch - a process that imports only the alembic environment does NOT
drag in ``api.settings``. delete the ``migrate`` service or add one settings
import under ``api/models/`` and the data tests all stay green.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.database.main as database_module
from api.boot_settings import boot_settings
from api.permissions import DefaultPermissions
from api.settings.database import _load_db_overrides
from api.settings.settings import DefaultPermissionsSettings, Settings
from api.tests.conftest import _create_isolated_test_database_url, _drop_database


# the revision whose block 16 rewrote three renamed and two removed permission
# names; "<rev>-1" is alembic's relative syntax for the revision just before it.
PERMISSIONS_REWRITE_REVISION = "8e77a463213f"
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
	"""the premise: what is REALLY IN the pre-migration store is rejected.

	the payload is read back out of the database rather than asserted against
	the module constant that was written in, so this fails if the fixture ever
	stops producing a store that would actually break a boot - which is the
	whole reason the migrate service is ordered ahead of every importer.

	the settings document is validated by ``DefaultPermissionsSettings`` in
	production. ``DefaultPermissions`` is asserted here because both declare
	``action_permissions`` over the same ``PermissionGrant`` union and reject
	the same names; either one demonstrates the premise.
	"""
	_url, engine = stale_store
	stored = _stored_permissions(engine)
	assert set(stored) == set(STALE_ACTION_PERMISSIONS), (
		"the fixture no longer writes a store that predates the rewrite"
	)
	with pytest.raises(ValueError):
		DefaultPermissions.model_validate({"action_permissions": stored})
	with pytest.raises(ValueError):
		DefaultPermissionsSettings.model_validate({"action_permissions": stored})


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
	# the crash comes from CONSTRUCTING the model, so construct it here -
	# `_load_db_overrides` returns dicts and never builds one itself.
	loaded = DefaultPermissionsSettings.model_validate(section)
	assert {str(value) for value in loaded.action_permissions} == (
		MIGRATED_ACTION_PERMISSIONS
	)


# --- the ordering half: cheap static assertions, no database ---

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE_FILES = (
	_REPO_ROOT / ".docker" / "docker-compose.yml",
	_REPO_ROOT / ".docker" / "docker-compose.local.yml",
)
_ENTRYPOINT = _REPO_ROOT / "backend" / "docker-entrypoint.sh"

#: every service that imports the app. taskiq is included deliberately: its
#: entrypoints read settings at import just like the API does.
_GATED_SERVICES = ("backend", "taskiq-worker", "taskiq-scheduler")


@pytest.mark.parametrize("compose_path", _COMPOSE_FILES, ids=lambda p: p.name)
def test_every_app_service_waits_for_the_migrate_service(compose_path: Path) -> None:
	"""the gate itself, in both stacks."""
	compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
	services = compose["services"]

	migrate = services.get("migrate")
	assert migrate is not None, "the one-shot migrator is gone"
	assert migrate["environment"]["RUN_MIGRATIONS"] == "1", (
		"the migrator no longer triggers the entrypoint's upgrade"
	)

	for name in _GATED_SERVICES:
		service = services.get(name)
		if service is None:
			continue
		depends_on = service.get("depends_on") or {}
		assert depends_on.get("migrate", {}).get("condition") == (
			"service_completed_successfully"
		), f"{name} no longer waits for migrations to finish"
		# migrations are not schema-only (one talks to qdrant), so the migrator
		# needs every backing service its gated services need; siblings excluded.
		backing_services = set(depends_on) - {"migrate", *_GATED_SERVICES}
		assert backing_services <= set(migrate["depends_on"]), (
			f"{name} depends on backing services the migrator does not: "
			f"{sorted(backing_services - set(migrate['depends_on']))}"
		)


def test_the_entrypoint_gates_the_upgrade_on_run_migrations() -> None:
	"""exactly one service migrates, and it is the one that sets the flag.

	running the upgrade in all three concurrently would race on the version
	table, which is why the image shares an entrypoint and branches instead.
	"""
	script = _ENTRYPOINT.read_text(encoding="utf-8")
	assert "RUN_MIGRATIONS:-0" in script
	assert "alembic" in script
	# and it honours the branching setting, exactly like `init_db` does.
	assert "BRANCHING_MIGRATIONS" in script
	assert "heads" in script


def test_the_alembic_environment_does_not_import_settings() -> None:
	"""the premise the whole bridge rests on, in a COLD interpreter.

	if the migration environment pulled in ``api.settings``, the migrator
	process would perform the very import-time read it exists to run ahead of -
	and would crash on exactly the stale store it was started to repair. this
	holds today only because ``env.py`` reaches for ``api.models`` and the
	single settings import under ``api/models/`` is lazy, inside a property
	body. that is a fragile fact, so it is pinned rather than assumed.

	``env.py`` itself cannot be imported without a live alembic context, so its
	module-scope imports are read from source and then performed cold. a new
	settings import added to that header fails the first half; one added
	anywhere under ``api.models`` fails the second.
	"""
	env_source = (_REPO_ROOT / "backend" / "api" / "migrations" / "env.py").read_text(
		encoding="utf-8"
	)
	tree = ast.parse(env_source)
	imported: list[str] = []
	for node in tree.body:
		if isinstance(node, ast.Import):
			imported.extend(alias.name for alias in node.names)
		elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
			imported.append(node.module)
	assert not any(
		name == "api.settings" or name.startswith("api.settings.") for name in imported
	), f"env.py now imports api.settings directly: {imported}"

	_assert_cold_import_is_settings_free(
		imported,
		"the alembic environment's imports now drag in api.settings, which "
		"defeats the migrate-before-serve ordering",
	)


def test_the_migrations_application_import_does_not_pull_in_settings() -> None:
	"""block 16 reaches into the application, and that reach must stay cheap.

	``_verify_action_permissions`` imports ``api.permissions.permission_grant``
	so it validates with the SAME parser the application runs rather than a
	restatement of it. that is only safe while ``api.permissions`` is a leaf:
	if it ever pulled in ``api.settings``, the verification step at the END of
	the migration would trigger the import-time settings read against a store
	the migration has not finished rewriting - turning the check that exists to
	prevent a boot crash into the cause of one.
	"""
	_assert_cold_import_is_settings_free(
		["api.permissions"],
		"api.permissions is no longer a leaf module: importing it drags in "
		"api.settings, so the migration's verification step would read the "
		"settings store mid-migration",
	)


def _assert_cold_import_is_settings_free(
	modules: list[str],
	message: str,
) -> None:
	"""import modules in a COLD interpreter and assert api.settings stays out.

	a subprocess is the whole point: by the time this test runs, conftest has
	imported most of the app, so ``api.settings`` is already in ``sys.modules``
	and an in-process check would pass no matter what.
	"""
	statement = "; ".join(f"import {name}" for name in modules)
	result = subprocess.run(
		[
			sys.executable,
			"-c",
			f"import sys; {statement}; "
			"sys.exit(1 if 'api.settings' in sys.modules else 0)",
		],
		capture_output=True,
		text=True,
		check=False,
		cwd=_REPO_ROOT / "backend",
	)
	assert result.returncode == 0, f"{message}:\n{result.stderr}"
