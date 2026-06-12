"""Pytest configuration and fixtures for API tests."""

from __future__ import annotations

import atexit
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
import pytest_asyncio
import redis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import (
	AsyncEngine,
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)

from api.models.model import ModelType
from api.models.user import User
from api.permissions import ActionPermission
from api.schemas.model import ModelCreate
from api.schemas.provider import ProviderCreate
from api.settings import settings
from api.storage import _BACKENDS, register
from api.storage.local import LocalStorageBackend
from api.v1.service import models as model_service
from api.v1.service import providers as provider_service
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service.auth import Principal
from nokodo_ai.embeddings import EmbeddingModel
from nokodo_ai.utils.security import hash_password


@pytest.fixture(scope="session", autouse=True)
def _register_test_storage_backends(
	tmp_path_factory: pytest.TempPathFactory,
) -> Generator[None]:
	"""register the local storage backend for the test session.

	uses a dedicated temp dir so test uploads do not pollute the project
	tree and are cleaned up automatically when the session ends.
	"""

	root = tmp_path_factory.mktemp("storage", numbered=True)
	register("local", LocalStorageBackend(root_path=str(root)))
	yield
	_BACKENDS.clear()


@pytest.fixture(scope="session", autouse=True)
def _api_test_env_defaults() -> Generator[None]:
	"""Make api tests self-contained (no external OpenAI/vector DB required)."""
	from api.boot_settings import boot_settings

	boot_settings.TESTING = True

	monkeypatch = pytest.MonkeyPatch()
	if not os.getenv("OPENAI_API_KEY"):
		monkeypatch.setenv("OPENAI_API_KEY", "test")
	if not os.getenv("NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__URL"):
		monkeypatch.setenv("NOKODO__ASSETS__VECTOR_DATABASE__QDRANT__URL", ":memory:")
	monkeypatch.setenv("NOKODO__SECURITY__AUTO_SIGNUP_ROLE_IDS", "[]")

	settings.reload()
	settings.security.auto_signup_role_ids = []
	settings.default_permissions.action_permissions = [
		ActionPermission.SETTINGS_READ,
		ActionPermission.THREADS_CREATE,
		ActionPermission.PROJECTS_CREATE,
		ActionPermission.NOTES_CREATE,
		ActionPermission.GROUPS_CREATE,
		ActionPermission.REMINDERS_CREATE,
		ActionPermission.MEMORIES_CREATE,
		ActionPermission.TASKS_CREATE,
		ActionPermission.FILES_CREATE,
		ActionPermission.USER_FRIENDSHIPS_CREATE,
		ActionPermission.USER_BLOCKS_CREATE,
	]
	try:
		yield
	finally:
		monkeypatch.undo()


@pytest.fixture(autouse=True)
def _api_test_stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Stub embeddings and vectorstore ops so tests don't need Qdrant."""

	vectorstores_service._vectorstore_adapter.cache_clear()
	vectorstores_service._cached_collection_name = None

	async def _fake_embed(
		self: EmbeddingModel, texts: list[str], input_type: str | None = None
	) -> list[list[float]]:
		_ = self
		return [[0.0, 0.0, 0.0, 0.0] for _ in texts]

	monkeypatch.setattr(EmbeddingModel, "embed", _fake_embed)

	# stub vectorstore CRUD so no Qdrant connection is needed
	async def _noop_upsert(*args: object, **kwargs: object) -> None:
		pass

	async def _noop_delete(*args: object, **kwargs: object) -> None:
		pass

	async def _noop_search(*args: object, **kwargs: object) -> list[object]:
		return []

	monkeypatch.setattr(vectorstores_service, "upsert_chunks", _noop_upsert)
	monkeypatch.setattr(vectorstores_service, "delete", _noop_delete)
	monkeypatch.setattr(vectorstores_service, "search", _noop_search)


@pytest.fixture(autouse=True)
def _api_test_cap_import_write_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Bound the Open WebUI import fan-out so the suite can't exhaust Postgres.

	the import fans out ``db_write_concurrency`` consumer sessions on top of the
	caller's own connection, each a distinct connection (the per-test engine
	uses NullPool, so connections track live work). pytest-xdist runs workers as
	separate processes, so an in-process semaphore cannot coordinate them - the
	only cross-process ceiling is the server's ``max_connections``. this product
	(workers * per-import connections) is the one thing that scales with both
	test- and process-level concurrency, so an unbounded fan-out overruns the
	ceiling regardless of how the suite is launched. pinning it to 1 keeps each
	worker's import peak at two connections (caller + one consumer), so the
	worst case stays far below the server limit at any ``-n``. the dedicated
	concurrency test overrides this with a higher value to still exercise the
	overlapping write path on a single worker.
	"""
	monkeypatch.setattr(settings.integrations.open_webui, "db_write_concurrency", 1)


@pytest.fixture(autouse=True)
def _api_test_neutralize_durable_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
	"""prevent durable task enqueues from hitting the (unstarted) Redis broker.

	unit tests never run a TaskIQ worker, so the global broker is never started.
	stubbing kick lets service primitives (e.g. store_file) enqueue background
	work without TESTING-only branches in production code. test_tasks.py rebinds
	its own InMemoryBroker, so this global stub does not affect it.
	"""
	from api.taskiq import broker

	async def _noop_kick(*args: object, **kwargs: object) -> None:
		pass

	monkeypatch.setattr(broker, "kick", _noop_kick)


@pytest_asyncio.fixture(autouse=True)
async def _api_test_seed_default_embedding_model(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Ensure a usable default embedding model exists for memory flows."""

	principal = Principal(
		user=User(
			email="seed@example.com",
			username="seed_test",
			hashed_password="x",
			is_superuser=True,
		),
		group_ids=(),
		permissions=frozenset({"providers:manage", "models:manage"}),
	)

	provider = await provider_service.create_provider(
		ProviderCreate(
			name="seed-openai",
			adapter_type="openai",
			api_key="test",
		),
		db_session,
		principal=principal,
	)

	model = await model_service.create_model(
		ModelCreate(
			provider_id=str(provider.id),
			name="seed-embedding",
			model_type=ModelType.EMBEDDING,
		),
		db_session,
		principal=principal,
	)

	monkeypatch.setenv(
		"NOKODO__ASSETS__DEFAULT_EMBEDDING_MODEL_ID",
		str(model.id),
	)
	settings.reload()
	# DbSettingsSource has higher priority than env_settings, so the env
	# var may be overridden by a production DB value. set it explicitly.
	settings.assets.default_embedding_model_id = str(model.id)
	settings.security.auto_signup_role_ids = []
	settings.default_permissions.action_permissions = [
		ActionPermission.SETTINGS_READ,
		ActionPermission.THREADS_CREATE,
		ActionPermission.PROJECTS_CREATE,
		ActionPermission.NOTES_CREATE,
		ActionPermission.GROUPS_CREATE,
		ActionPermission.REMINDERS_CREATE,
		ActionPermission.MEMORIES_CREATE,
		ActionPermission.TASKS_CREATE,
		ActionPermission.FILES_CREATE,
		ActionPermission.USER_FRIENDSHIPS_CREATE,
		ActionPermission.USER_BLOCKS_CREATE,
	]


_CI_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_ci_run() -> bool:
	value = os.getenv("CI")
	if not value:
		return False
	return value.strip().lower() in _CI_TRUE_VALUES


class AdminConnectionUnavailableError(RuntimeError):
	"""Raised when a privileged Postgres connection cannot be established."""


def _derive_test_database_template_url() -> URL:
	"""Build the base Postgres URL used to mint ephemeral test databases."""
	override = os.getenv("TEST_DATABASE_URL")
	if override:
		template_url = make_url(override)
	else:
		try:
			database_url = make_url(os.environ["DATABASE_URL"])
		except KeyError:
			from api.boot_settings import boot_settings

			database_url = make_url(boot_settings.DATABASE_URL)
		if not database_url.database:
			raise RuntimeError("DATABASE_URL must include a database name for tests")
		template_url = database_url

	if template_url.drivername not in {"postgresql", "postgresql+psycopg"}:
		raise RuntimeError(
			f"Tests require a Postgres database, got driver '{template_url.drivername}'"
		)

	if not template_url.database:
		raise RuntimeError("Test database URL must include a database name")

	return template_url


def _create_database(url: URL) -> None:
	"""Create a Postgres database owned by the template user."""
	if not url.database:
		raise RuntimeError("Test database URL must include a database name")

	_ensure_template_role_exists()
	_drop_database(url)
	template_url = _template_url()
	owner = template_url.username
	owner_clause = f" OWNER {_quote_ident(owner)}" if owner else ""
	create_sql = text(f"CREATE DATABASE {_quote_ident(url.database)}{owner_clause}")

	try:
		with _admin_connection() as conn:
			conn.execute(create_sql)
			return
	except AdminConnectionUnavailableError:
		pass

	with _owner_connection() as conn:
		conn.execute(create_sql)


def _drop_database(url: URL) -> None:
	"""Drop a Postgres database if it exists, terminating active connections."""
	if not url.database:
		return

	drop_sql = text(f"DROP DATABASE IF EXISTS {_quote_ident(url.database)}")
	try:
		with _admin_connection() as conn:
			conn.execute(
				text(
					"""
					SELECT pg_terminate_backend(pid)
					FROM pg_stat_activity
					WHERE datname = :name AND pid <> pg_backend_pid()
					"""
				),
				{"name": url.database},
			)
			conn.execute(drop_sql)
			return
	except AdminConnectionUnavailableError:
		pass

	with _owner_connection() as conn:
		conn.execute(drop_sql)


def _deduplicate_urls(urls: list[URL]) -> list[URL]:
	"""Remove duplicate URLs while preserving order."""
	seen: set[str] = set()
	unique: list[URL] = []
	for url in urls:
		key = url.render_as_string(hide_password=False)
		if key in seen:
			continue
		seen.add(key)
		unique.append(url)
	return unique


def _can_connect(url: URL) -> bool:
	"""Return whether the given SQLAlchemy URL can establish a connection."""
	engine = create_engine(url)
	try:
		with engine.connect() as conn:
			conn.execute(text("SELECT 1"))
		return True
	except OperationalError:
		return False
	finally:
		engine.dispose()


def _template_connection_available(url: URL) -> bool:
	"""Check whether template credentials can reach Postgres."""
	if _can_connect(url.set(database="postgres")):
		return True
	if url.database and url.database != "postgres":
		return _can_connect(url.set(database=url.database))
	return False


def _cleanup_leftover_test_databases() -> None:
	"""Drop any leftover per-test databases from prior runs."""
	base_name = _template_url().database or "nokodo_ai_test"
	pattern = f"{base_name}_test_%"
	try:
		with _admin_connection() as conn:
			rows = conn.execute(
				text(
					"""SELECT datname
FROM pg_database
WHERE datname LIKE :pattern
  AND datistemplate = false
"""
				),
				{"pattern": pattern},
			).fetchall()
			for (db_name,) in rows:
				conn.execute(
					text(
						"""
						SELECT pg_terminate_backend(pid)
						FROM pg_stat_activity
						WHERE datname = :name AND pid <> pg_backend_pid()
						"""
					),
					{"name": db_name},
				)
				conn.execute(text(f"DROP DATABASE IF EXISTS {_quote_ident(db_name)}"))
	except AdminConnectionUnavailableError:
		return


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
	_ = (session, exitstatus)
	if os.getenv("PYTEST_XDIST_WORKER"):
		return
	if _is_ci_run():
		return
	_cleanup_leftover_test_databases()
	_flush_isolated_test_redis()


def _find_available_port() -> int:
	"""Allocate an ephemeral TCP port bound to localhost."""
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
		sock.bind(("127.0.0.1", 0))
		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		return int(sock.getsockname()[1])


def _resolve_postgres_binary(binary: str) -> str:
	"""Locate a Postgres utility binary on PATH."""
	resolved = shutil.which(binary)
	if not resolved:
		raise RuntimeError(
			f"Unable to locate '{binary}' on PATH. Install Postgres or provide "
			"TEST_DATABASE_URL."
		)
	return resolved


def _rewrite_pg_hba_conf(data_dir: Path) -> None:
	"""Ensure the embedded cluster trusts local TCP connections."""
	hba_path = data_dir / "pg_hba.conf"
	hba_entries = [
		"local all all trust",
		"host all all 127.0.0.1/32 trust",
		"host all all ::1/128 trust",
	]
	hba_path.write_text("\n".join(hba_entries) + "\n", encoding="utf-8")


def _append_postgresql_conf(data_dir: Path) -> None:
	"""Force the embedded cluster to listen on localhost only."""
	conf_path = data_dir / "postgresql.conf"
	with conf_path.open("a", encoding="utf-8") as handle:
		handle.write("\nlisten_addresses = '127.0.0.1'\n")


class EmbeddedPostgresCluster:
	"""Run a private Postgres instance for tests when no host DB is available."""

	def __init__(self) -> None:
		self._data_dir = Path(tempfile.mkdtemp(prefix="nokodo_pg_"))
		self._port = _find_available_port()
		self._initdb = _resolve_postgres_binary("initdb")
		self._pg_ctl = _resolve_postgres_binary("pg_ctl")
		self._started = False

	def start(self) -> URL:
		self._run_initdb()
		_rewrite_pg_hba_conf(self._data_dir)
		_append_postgresql_conf(self._data_dir)
		self._run_pg_ctl("start", extra=["-o", f"-p {self._port} -F"])
		self._started = True
		atexit.register(self.stop)
		return make_url(
			f"postgresql+psycopg://postgres@127.0.0.1:{self._port}/postgres"
		)

	def stop(self) -> None:
		if not self._started:
			return
		self._run_pg_ctl("stop", extra=["-m", "fast"], check=False)
		shutil.rmtree(self._data_dir, ignore_errors=True)
		self._started = False

	def _run_initdb(self) -> None:
		result = subprocess.run(
			[
				self._initdb,
				"-A",
				"trust",
				"-U",
				"postgres",
				"-D",
				str(self._data_dir),
			],
			capture_output=True,
			text=True,
		)
		if result.returncode != 0:
			raise RuntimeError(
				"initdb failed while preparing embedded Postgres:\n"
				+ result.stderr.strip()
			)

	def _run_pg_ctl(
		self,
		action: str,
		extra: list[str] | None = None,
		check: bool = True,
	) -> None:
		args = [self._pg_ctl, "-D", str(self._data_dir)]
		if extra:
			args.extend(extra)
		args.extend(["-w", action])
		result = subprocess.run(
			args,
			capture_output=True,
			text=True,
		)
		if check and result.returncode != 0:
			raise RuntimeError(
				f"pg_ctl {action} failed for embedded Postgres:\n"
				+ result.stderr.strip()
			)


def _pgpass_candidate_paths() -> list[Path]:
	paths: list[Path] = []
	override = os.getenv("PGPASSFILE")
	if override:
		paths.append(Path(override).expanduser())
	home = os.path.expanduser("~")
	if home:
		paths.append(Path(home) / ".pgpass")
	if os.name == "nt":
		appdata = os.getenv("APPDATA")
		if appdata:
			paths.append(Path(appdata) / "postgresql" / "pgpass.conf")
	return paths


PGPASS_CANDIDATE_PATHS = _pgpass_candidate_paths()


def _parse_pgpass_line(line: str) -> list[str] | None:
	if not line or line.startswith("#"):
		return None
	parts: list[str] = []
	buffer: list[str] = []
	escaped = False
	for char in line.rstrip("\n"):
		if escaped:
			buffer.append(char)
			escaped = False
		elif char == "\\":
			escaped = True
		elif char == ":":
			parts.append("".join(buffer))
			buffer = []
		else:
			buffer.append(char)
	parts.append("".join(buffer))
	if len(parts) != 5:
		return None
	return parts


def _pgpass_field_matches(pattern: str, value: str | None) -> bool:
	if pattern == "*":
		return True
	return pattern == (value or "")


def _load_pgpass_passwords(url: URL) -> list[str]:
	host = url.host or "localhost"
	port = str(url.port or 5432)
	database = url.database or "*"
	user = url.username or "*"
	passwords: list[str] = []
	for path in PGPASS_CANDIDATE_PATHS:
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except FileNotFoundError:
			continue
		except OSError:
			continue
		for line in lines:
			parsed = _parse_pgpass_line(line.strip())
			if not parsed:
				continue
			entry_host, entry_port, entry_db, entry_user, entry_password = parsed
			if not (
				_pgpass_field_matches(entry_host, host)
				and _pgpass_field_matches(entry_port, port)
				and _pgpass_field_matches(entry_db, database)
				and _pgpass_field_matches(entry_user, user)
			):
				continue
			passwords.append(entry_password)
	return passwords


def _collect_password_candidates(template_url: URL) -> list[str | None]:
	candidate_values: list[str | None] = [
		template_url.password,
		os.getenv("TEST_DATABASE_PASSWORD"),
		os.getenv("DATABASE_PASSWORD"),
		os.getenv("DB_PASSWORD"),
		os.getenv("POSTGRES_PASSWORD"),
		os.getenv("PGPASSWORD"),
	]
	candidate_values.extend(_load_pgpass_passwords(template_url))
	candidate_values.extend(["nokodo-ai", "postgres", None])
	seen: set[str] = set()
	seen_none = False
	ordered: list[str | None] = []
	for candidate in candidate_values:
		if candidate is None:
			if seen_none:
				continue
			seen_none = True
			ordered.append(None)
			continue
		if candidate in seen:
			continue
		seen.add(candidate)
		ordered.append(candidate)
	return ordered


TEST_DATABASE_TEMPLATE_URL: URL | None = None
_TEMPLATE_ROLE_ENSURED = False
_TEMPLATE_ROLE_LOCK = Lock()
_TEMPLATE_ROLE_ADVISORY_LOCK_KEY = 0x6E6F4B4F444F  # "nokodo" in hex
_ADMIN_CONNECTION_URL_IN_USE: URL | None = None
_EMBEDDED_CLUSTER: EmbeddedPostgresCluster | None = None


def _template_url() -> URL:
	global TEST_DATABASE_TEMPLATE_URL
	global _EMBEDDED_CLUSTER
	if TEST_DATABASE_TEMPLATE_URL is not None:
		return TEST_DATABASE_TEMPLATE_URL

	template_url = _derive_test_database_template_url()
	if not _template_connection_available(template_url):
		try:
			_EMBEDDED_CLUSTER = EmbeddedPostgresCluster()
			template_url = _EMBEDDED_CLUSTER.start()
			port = template_url.port or 0
			print(f"[tests] started embedded Postgres cluster on port {port}")
		except RuntimeError as exc:  # pragma: no cover
			raise RuntimeError(
				"Unable to connect to TEST_DATABASE_URL and failed to start "
				"an embedded Postgres instance."
			) from exc

	TEST_DATABASE_TEMPLATE_URL = template_url
	return template_url


def _build_admin_database_urls(template_url: URL) -> list[URL]:
	override = os.getenv("TEST_DATABASE_ADMIN_URL")
	if override:
		admin_url = make_url(override)
		if not admin_url.database:
			admin_url = admin_url.set(database="postgres")
		return [admin_url]

	urls: list[URL] = []

	if template_url.username:
		template_passwords = _collect_password_candidates(template_url)
		for password in dict.fromkeys(template_passwords):
			urls.append(template_url.set(password=password, database="postgres"))

	user_candidates = ["postgres"]
	for user in dict.fromkeys(user_candidates):
		if not user:
			continue
		user_passwords = _collect_password_candidates(
			template_url.set(username=user, password=None, database=None)
		)
		for password in dict.fromkeys(user_passwords):
			urls.append(
				template_url.set(username=user, password=password, database="postgres")
			)

	if not urls:
		raise RuntimeError(
			"Unable to derive admin connection URL. Configure TEST_DATABASE_ADMIN_URL."
		)

	return _deduplicate_urls(urls)


def _quote_ident(value: str) -> str:
	return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
	return "'" + value.replace("'", "''") + "'"


def _connection_has_admin_rights(conn: Connection) -> bool:
	row = conn.execute(
		text(
			"""
			SELECT rolsuper, rolcreaterole, rolcreatedb
			FROM pg_roles
			WHERE rolname = current_user
			"""
		)
	).one_or_none()
	if row is None:
		return False
	rolsuper, rolcreaterole, rolcreatedb = row
	return bool(rolsuper or (rolcreaterole and rolcreatedb))


@contextmanager
def _admin_connection() -> Generator[Connection]:
	global _ADMIN_CONNECTION_URL_IN_USE
	last_error: Exception | None = None
	for admin_url in _build_admin_database_urls(_template_url()):
		engine = create_engine(admin_url)
		masked_url = admin_url.render_as_string(hide_password=True)
		try:
			with engine.connect() as raw_conn:
				conn = raw_conn.execution_options(isolation_level="AUTOCOMMIT")
				if not _connection_has_admin_rights(conn):
					last_error = RuntimeError(
						f"Admin connection '{masked_url}' lacks "
						"CREATEDB and CREATEROLE "
						"privileges"
					)
					continue
				_ADMIN_CONNECTION_URL_IN_USE = admin_url
				yield conn
				return
		except OperationalError as exc:  # pragma: no cover
			last_error = exc
		finally:
			engine.dispose()

	raise AdminConnectionUnavailableError(
		"Unable to establish a privileged Postgres connection for test database "
		"management. Set TEST_DATABASE_ADMIN_URL to a superuser connection string."
	) from last_error


@contextmanager
def _owner_connection() -> Generator[Connection]:
	template_url = _template_url()
	ddl_database = template_url.database or "postgres"
	owner_url = template_url.set(database=ddl_database)
	engine = create_engine(owner_url)
	try:
		raw_conn = engine.connect()
	except OperationalError as exc:
		engine.dispose()
		raise RuntimeError(
			"Unable to connect to Postgres using TEST_DATABASE_URL credentials. "
			"Ensure the configured user can create and drop databases."
		) from exc

	try:
		conn = raw_conn.execution_options(isolation_level="AUTOCOMMIT")
		yield conn
	finally:
		raw_conn.close()
		engine.dispose()


def _ensure_template_role_exists() -> None:
	global _TEMPLATE_ROLE_ENSURED
	template_url = _template_url()
	role = template_url.username
	password = template_url.password
	if _TEMPLATE_ROLE_ENSURED or not role:
		return

	with _TEMPLATE_ROLE_LOCK:
		if _TEMPLATE_ROLE_ENSURED:
			return

		probe_db = template_url.database or "postgres"
		probe_url = template_url.set(database=probe_db)
		if _can_connect(probe_url):
			_TEMPLATE_ROLE_ENSURED = True
			return

		try:
			with _admin_connection() as conn:
				conn.execute(
					text("SELECT pg_advisory_lock(:key)"),
					{"key": _TEMPLATE_ROLE_ADVISORY_LOCK_KEY},
				)
				try:
					role_exists = conn.execute(
						text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
						{"role": role},
					).scalar_one_or_none()

					create_clauses = ["LOGIN"]
					if password is not None:
						create_clauses.append(f"PASSWORD {_quote_literal(password)}")
					create_sql = (
						f"CREATE ROLE {_quote_ident(role)} {' '.join(create_clauses)}"
					)

					if not role_exists:
						conn.execute(text(create_sql))
					elif password is not None:
						try:
							conn.execute(
								text(
									"ALTER ROLE "
									+ f"{_quote_ident(role)} "
									+ f"PASSWORD {_quote_literal(password)}"
								)
							)
						except ProgrammingError as exc:
							raise RuntimeError(
								f"Unable to update Postgres role '{role}'. "
								"Provide TEST_DATABASE_ADMIN_URL with a superuser "
								"connection."
							) from exc
				finally:
					conn.execute(
						text("SELECT pg_advisory_unlock(:key)"),
						{"key": _TEMPLATE_ROLE_ADVISORY_LOCK_KEY},
					)
		except AdminConnectionUnavailableError as exc:
			raise RuntimeError(
				f"Unable to ensure Postgres role '{role}'. "
				"Provide TEST_DATABASE_ADMIN_URL with a superuser connection."
			) from exc

	_TEMPLATE_ROLE_ENSURED = True


def _create_isolated_test_database_url() -> URL:
	template_url = _template_url()
	base_name = template_url.database or "nokodo_ai_test"
	suffix = uuid4().hex[:8]
	db_name = f"{base_name}_test_{suffix}"
	url = template_url.set(database=db_name)
	_create_database(url)
	return url


async def _create_async_engine_with_fallback(url: URL) -> AsyncEngine:
	candidates: list[URL] = [url]
	if _ADMIN_CONNECTION_URL_IN_USE is not None:
		candidates.append(_ADMIN_CONNECTION_URL_IN_USE.set(database=url.database))
	candidates = _deduplicate_urls(candidates)
	errors: list[Exception] = []
	for candidate in candidates:
		# a small bounded pool, not NullPool. NullPool opens a fresh socket per
		# operation; across the whole suite that churn exhausts the Windows
		# ephemeral TCP port range (connections linger in TIME_WAIT) and raises
		# "Address already in use". a QueuePool reuses connections so socket
		# churn stays low, while a low pool_size + max_overflow caps each
		# worker's connections so workers * pool-total stays under the server's
		# max_connections at any -n concurrency. the import fan-out is bounded
		# separately (see _api_test_cap_import_write_concurrency) so a single
		# test never needs more than this pool provides.
		engine = create_async_engine(
			candidate.render_as_string(hide_password=False),
			echo=False,
			pool_size=2,
			max_overflow=5,
			pool_timeout=30,
		)
		try:
			async with engine.connect() as conn:
				await conn.execute(text("SELECT 1"))
		except OperationalError as exc:
			errors.append(exc)
			await engine.dispose()
			continue
		return engine

	raise RuntimeError(
		"Unable to connect to Postgres using test database credentials. "
		"Set DATABASE_URL or TEST_DATABASE_ADMIN_URL to a working user."
	) from (errors[-1] if errors else None)


def _isolated_test_redis_url() -> str:
	"""Return ``REDIS_URL`` repointed at the isolated test logical DB.

	The dev/prod redis DB (the path in ``settings.cache.redis.url``) is left
	untouched; tests use ``TEST_REDIS_DB`` (default ``15``) so their pub/sub
	and task-bus writes can never collide with live redis state.
	"""
	test_db = int(os.getenv("TEST_REDIS_DB", "15"))
	parts = urlsplit(settings.cache.redis.url)
	return urlunsplit(parts._replace(path=f"/{test_db}"))


def _flush_isolated_test_redis() -> None:
	"""Best-effort flush of the isolated test redis DB after a run.

	Equivalent to dropping the per-test Postgres databases: it clears the
	dedicated test namespace so leftover keys never accumulate. Failures
	(e.g. redis unavailable at teardown) are ignored so they cannot fail the
	run.
	"""
	try:
		client = redis.from_url(_isolated_test_redis_url())
		try:
			client.flushdb()
		finally:
			client.close()
	except OSError, redis.exceptions.RedisError:
		return


@pytest_asyncio.fixture(scope="function", loop_scope="function", autouse=True)
async def _api_test_redis_lifecycle() -> AsyncGenerator[None]:
	"""Connect the singleton redis client to an isolated test DB per test.

	Mirrors the per-test Postgres isolation: real functionality lives on the
	dev/prod redis logical DB (the one in ``REDIS_URL``, default ``0``) while
	tests run against a dedicated logical DB (``TEST_REDIS_DB``, default
	``15``). Task-bus and run-bus writes made by service primitives therefore
	land in a namespace that real redis features never read, so the suite can
	never clobber or be clobbered by live redis state. TaskIQ stays isolated
	separately because ``broker.kick`` is stubbed (durable enqueues no-op).

	Function scope binds the connection pool to each test's running loop, and
	the teardown closes it on that same loop. Tests use the same valkey
	instance the dev stack starts on ``REDIS_URL``; CI ensures a valkey
	container is available. There is no in-process fallback - if connection
	fails, tests fail fast.
	"""
	from api.redis import redis_client

	# connect() is idempotent and the prior test's teardown already closed the
	# singleton, so this opens a fresh pool bound to the current test loop.
	await redis_client.connect(url=_isolated_test_redis_url())
	try:
		yield
	finally:
		await redis_client.aclose()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
	# Import models/Base at runtime so coverage sees them.
	import api.database.main as _db_module
	import api.models as _models
	from api.models.base import Base

	_ = _models

	test_db_url = _create_isolated_test_database_url()
	engine = await _create_async_engine_with_fallback(test_db_url)

	original_session_factory = _db_module._async_session_factory
	try:
		async with engine.begin() as conn:
			await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
			await conn.run_sync(Base.metadata.create_all)

		test_session_local = async_sessionmaker(
			engine,
			class_=AsyncSession,
			expire_on_commit=False,
			autocommit=False,
			autoflush=False,
		)

		# patch the module-level session factory so internal code
		# (e.g. event fan-out) uses the test database, not the main one
		original_session_factory = _db_module._async_session_factory
		_db_module._async_session_factory = test_session_local

		async with test_session_local() as session:
			yield session
	finally:
		_db_module._async_session_factory = original_session_factory
		await engine.dispose()
		_drop_database(test_db_url)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
	from api.boot_settings import boot_settings

	previous_testing = boot_settings.TESTING
	boot_settings.TESTING = True

	from api.database import get_db
	from api.main import app

	# ensure a local storage backend is available even if the session-scoped
	# fixture was torn down or cleared by another test
	_needs_storage = "local" not in _BACKENDS
	if _needs_storage:
		register("local", LocalStorageBackend(root_path=str(Path(tempfile.mkdtemp()))))

	async def override_get_db() -> AsyncGenerator[AsyncSession]:
		yield db_session

	app.dependency_overrides[get_db] = override_get_db

	async with AsyncClient(
		transport=ASGITransport(app=app),
		base_url="http://test",
	) as test_client:
		yield test_client

	app.dependency_overrides.clear()
	boot_settings.TESTING = previous_testing


@pytest_asyncio.fixture(scope="function")
async def admin_auth(client: AsyncClient) -> dict[str, object]:
	uniq = uuid4().hex[:10]
	email = f"admin{uniq}@example.com"
	username = f"admin{uniq}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": True,
		},
	)
	assert user_resp.status_code == 201
	user = user_resp.json()

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	return {
		"user": user,
		"token": token,
		"headers": {"Authorization": f"Bearer {token}"},
		"email": email,
		"password": password,
	}


@pytest_asyncio.fixture(scope="function")
async def user_auth(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> dict[str, object]:
	uniq = uuid4().hex[:10]
	email = f"user{uniq}@example.com"
	username = f"user{uniq}"
	password = "password"
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	user_resp = await client.post(
		"/v1/users",
		headers={str(k): str(v) for k, v in headers.items()},
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201
	user = user_resp.json()

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	return {
		"user": user,
		"token": token,
		"headers": {"Authorization": f"Bearer {token}"},
		"email": email,
		"password": password,
	}


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> dict[str, object]:
	user = User(
		email="test@example.com",
		username="test_user",
		hashed_password=hash_password("password"),
		is_active=True,
		is_superuser=False,
	)
	db_session.add(user)
	await db_session.commit()
	await db_session.refresh(user)

	return {"id": user.id, "email": user.email}
