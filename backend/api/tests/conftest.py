"""Pytest configuration and fixtures."""

from __future__ import annotations

import asyncio
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
from uuid import uuid4

import pytest
import pytest_asyncio
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

# Ensure SQLAlchemy models are registered with Base metadata for DDL operations
from api.core.config import settings
from api.core.database import Base


# Configure settings for tests before importing the app
settings.TESTING = True


class AdminConnectionUnavailableError(RuntimeError):
	"""Raised when a privileged Postgres connection cannot be established."""


def _derive_test_database_template_url() -> URL:
	"""Build the base Postgres URL used to mint ephemeral test databases."""
	override = os.getenv("TEST_DATABASE_URL")
	if override:
		template_url = make_url(override)
	else:
		database_url = make_url(str(settings.DATABASE_URL))
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
	owner = TEST_DATABASE_TEMPLATE_URL.username
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
	# Prefer connecting to the built-in maintenance DB so tests do not touch the
	# application's dev database.
	if _can_connect(url.set(database="postgres")):
		return True
	# Fallback for environments where the user has access only to a specific DB.
	if url.database and url.database != "postgres":
		return _can_connect(url.set(database=url.database))
	return False


def _cleanup_leftover_test_databases() -> None:
	"""Drop any leftover per-test databases from prior runs.

	This is a safety net for interrupted runs; the per-test fixture still drops
	its own database in a finally block.
	"""
	base_name = TEST_DATABASE_TEMPLATE_URL.database or "nokodo_ai_test"
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
		# If we can't get a privileged connection, cleanup is best-effort.
		return


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:  # noqa: ARG001
	"""Ensure no per-test databases remain after the suite completes."""
	# In xdist, run cleanup only once from the controller process.
	if os.getenv("PYTEST_XDIST_WORKER"):
		return
	_cleanup_leftover_test_databases()


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
		"""Initialize and launch the embedded Postgres cluster."""
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
		"""Terminate the embedded cluster if it is running."""
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
		self, action: str, extra: list[str] | None = None, check: bool = True
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
	"""Return possible pgpass file locations for the current platform."""
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
	"""Parse a pgpass line into its five fields, handling escapes."""
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
	"""Return whether a pgpass field matches the provided value."""
	if pattern == "*":
		return True
	return pattern == (value or "")


def _load_pgpass_passwords(url: URL) -> list[str]:
	"""Load matching passwords from known pgpass files."""
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
	"""Assemble the ordered list of password guesses for Postgres connections."""
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


TEST_DATABASE_TEMPLATE_URL = _derive_test_database_template_url()
_TEMPLATE_ROLE_ENSURED = False
_TEMPLATE_ROLE_LOCK = Lock()
_TEMPLATE_ROLE_ADVISORY_LOCK_KEY = 0x6E6F4B4F444F  # "nokodo" in hex
_ADMIN_CONNECTION_URL_IN_USE: URL | None = None
_EMBEDDED_CLUSTER: EmbeddedPostgresCluster | None = None

if not _template_connection_available(TEST_DATABASE_TEMPLATE_URL):
	try:
		_EMBEDDED_CLUSTER = EmbeddedPostgresCluster()
		TEST_DATABASE_TEMPLATE_URL = _EMBEDDED_CLUSTER.start()
		port = TEST_DATABASE_TEMPLATE_URL.port or 0
		print(f"[tests] started embedded Postgres cluster on port {port}")
	except RuntimeError as exc:  # pragma: no cover - requires local failure
		raise RuntimeError(
			"Unable to connect to TEST_DATABASE_URL and failed to start an embedded "
			"Postgres instance."
		) from exc


def _build_admin_database_urls(template_url: URL) -> list[URL]:
	"""Generate candidate admin URLs for managing disposable databases."""
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
			urls.append(
				template_url.set(
					password=password,
					database="postgres",
				)
			)

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
	"""Quote identifiers for raw SQL statements."""
	return f'"{value.replace('"', '""')}"'


def _quote_literal(value: str) -> str:
	"""Quote string literals for raw SQL statements."""
	return f"'{value.replace("'", "''")}'"


def _connection_has_admin_rights(conn: Connection) -> bool:
	"""Check whether the current connection can manage roles and databases."""
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
	"""Yield a Postgres connection using the first admin URL with required rights."""
	global _ADMIN_CONNECTION_URL_IN_USE
	last_error: Exception | None = None
	for admin_url in _build_admin_database_urls(TEST_DATABASE_TEMPLATE_URL):
		engine = create_engine(admin_url)
		masked_url = admin_url.render_as_string(hide_password=True)
		try:
			with engine.connect() as raw_conn:
				conn = raw_conn.execution_options(isolation_level="AUTOCOMMIT")
				if not _connection_has_admin_rights(conn):
					last_error = RuntimeError(
						f"Admin connection '{masked_url}' lacks CREATEDB and "
						"CREATEROLE privileges"
					)
					continue
				_ADMIN_CONNECTION_URL_IN_USE = admin_url
				print(f"[tests] admin connection established via {masked_url}")
				yield conn
				return
		except OperationalError as exc:  # pragma: no cover - exercised in CI
			last_error = exc
		finally:
			engine.dispose()

	raise AdminConnectionUnavailableError(
		"Unable to establish a privileged Postgres connection for test database "
		"management. Set TEST_DATABASE_ADMIN_URL to a superuser connection string."
	) from last_error


@contextmanager
def _owner_connection() -> Generator[Connection]:
	"""Yield a Postgres connection using the template credentials for DDL fallback."""
	ddl_database = TEST_DATABASE_TEMPLATE_URL.database or "postgres"
	owner_url = TEST_DATABASE_TEMPLATE_URL.set(database=ddl_database)
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
	"""Ensure the disposable database owner role exists before creating DBs."""
	global _TEMPLATE_ROLE_ENSURED
	role = TEST_DATABASE_TEMPLATE_URL.username
	password = TEST_DATABASE_TEMPLATE_URL.password
	if _TEMPLATE_ROLE_ENSURED or not role:
		return

	with _TEMPLATE_ROLE_LOCK:
		if _TEMPLATE_ROLE_ENSURED:
			return

		probe_db = TEST_DATABASE_TEMPLATE_URL.database or "postgres"
		probe_url = TEST_DATABASE_TEMPLATE_URL.set(database=probe_db)
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
									f"{_quote_ident(role)} "
									f"PASSWORD {_quote_literal(password)}"
								)
							)
						except ProgrammingError as exc:
							raise RuntimeError(
								f"Unable to update Postgres role '{role}'. "
								"Provide TEST_DATABASE_ADMIN_URL with a superuser "
								"connection or set the password manually."
							) from exc
				finally:
					conn.execute(
						text("SELECT pg_advisory_unlock(:key)"),
						{"key": _TEMPLATE_ROLE_ADVISORY_LOCK_KEY},
					)
		except AdminConnectionUnavailableError as exc:
			raise RuntimeError(
				f"Unable to ensure Postgres role '{role}'. "
				"Provide TEST_DATABASE_ADMIN_URL with a superuser connection or "
				"supply working TEST_DATABASE_URL credentials."
			) from exc

		_TEMPLATE_ROLE_ENSURED = True


def _create_isolated_test_database_url() -> URL:
	"""Mint a unique Postgres database URL for a single test case."""
	base_name = TEST_DATABASE_TEMPLATE_URL.database or "nokodo_ai_test"
	suffix = uuid4().hex[:8]
	db_name = f"{base_name}_test_{suffix}"
	url = TEST_DATABASE_TEMPLATE_URL.set(database=db_name)
	_create_database(url)
	return url


async def _create_async_engine_with_fallback(url: URL) -> AsyncEngine:
	"""Create an async engine, falling back to an admin user if template creds fail."""
	candidates: list[URL] = [url]
	if _ADMIN_CONNECTION_URL_IN_USE is not None:
		candidates.append(_ADMIN_CONNECTION_URL_IN_USE.set(database=url.database))
	candidates = _deduplicate_urls(candidates)
	errors: list[Exception] = []
	for candidate in candidates:
		print(
			"[tests] attempting async engine connection via "
			f"{candidate.render_as_string(hide_password=True)}"
		)
		engine = create_async_engine(
			candidate.render_as_string(hide_password=False), echo=False
		)
		try:
			async with engine.connect() as conn:
				await conn.execute(text("SELECT 1"))
		except OperationalError as exc:
			print(f"[tests] connection attempt failed: {exc.__class__.__name__}: {exc}")
			errors.append(exc)
			await engine.dispose()
			continue
		return engine

	raise RuntimeError(
		"Unable to connect to Postgres using test database credentials. "
		"Set DATABASE_URL or TEST_DATABASE_ADMIN_URL to a working user."
	) from (errors[-1] if errors else None)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
	"""Create an instance of the default event loop for the test session."""
	loop = asyncio.get_event_loop_policy().new_event_loop()
	yield loop
	loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
	"""Create a test database session backed by an isolated Postgres DB."""
	test_db_url = _create_isolated_test_database_url()
	engine = await _create_async_engine_with_fallback(test_db_url)

	try:
		async with engine.begin() as conn:
			await conn.run_sync(Base.metadata.create_all)

		test_session_local = async_sessionmaker(
			engine,
			class_=AsyncSession,
			expire_on_commit=False,
			autocommit=False,
			autoflush=False,
		)

		async with test_session_local() as session:
			yield session
	finally:
		await engine.dispose()
		_drop_database(test_db_url)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
	"""Create a test client with overridden database dependency."""

	# Import after TESTING flag is set to avoid startup DB init
	from api.core.database import get_db
	from api.main import app
	from api.v1.app import v1_app

	async def override_get_db() -> AsyncGenerator[AsyncSession]:
		yield db_session

	app.dependency_overrides[get_db] = override_get_db
	v1_app.dependency_overrides[get_db] = override_get_db

	async with AsyncClient(
		transport=ASGITransport(app=app), base_url="http://test"
	) as test_client:
		yield test_client

	app.dependency_overrides.clear()
	v1_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> dict:
	"""Create a test user."""
	from api.models.user import User

	user = User(
		email="test@example.com",
		hashed_password="hashed_password",
		is_active=True,
		is_superuser=False,
	)
	db_session.add(user)
	await db_session.commit()
	await db_session.refresh(user)

	return {
		"id": user.id,
		"email": user.email,
	}
