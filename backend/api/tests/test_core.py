"""Tests for configuration validators and database helpers."""

from __future__ import annotations

import logging
import types
from unittest.mock import MagicMock

import pytest

from api import runtime as config_module
from api import runtime as runtime_module
from api.boot_settings import BootSettings
from api.database import main as database_module
from api.settings.settings import SecuritySettings


class _DummySession:
	"""Lightweight async session stand-in for exercising get_db."""

	def __init__(self) -> None:
		self.committed = False
		self.rolled_back = False
		self.closed = False

	async def commit(self) -> None:
		self.committed = True

	async def rollback(self) -> None:
		self.rolled_back = True

	async def close(self) -> None:
		self.closed = True


class _DummySessionContext:
	"""Provides the async context manager protocol used by AsyncSession."""

	def __init__(self, session: _DummySession) -> None:
		self._session = session
		self.exited = False

	async def __aenter__(self) -> _DummySession:
		return self._session

	async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
		self.exited = True


class _DummyConnection:
	def __init__(self) -> None:
		self.called_with: object = None

	async def run_sync(self, fn: object) -> None:
		self.called_with = fn


class _DummyEngine:
	def __init__(self, connection: _DummyConnection) -> None:
		self._connection = connection

	def begin(self) -> object:
		connection = self._connection

		class _BeginContext:
			async def __aenter__(self) -> _DummyConnection:
				return connection

			async def __aexit__(
				self, exc_type: object, exc: object, tb: object
			) -> bool:  # pragma: no cover
				return False

		return _BeginContext()


def test_settings_parse_cors_origins_from_string() -> None:
	security = SecuritySettings.model_validate(
		{"cors_origins": "https://a.com, https://b.com"}
	)
	assert security.cors_origins == ["https://a.com", "https://b.com"]


def test_settings_validate_database_url_scheme() -> None:
	with pytest.raises(ValueError):
		BootSettings(DATABASE_URL="mysql://localhost/db")


def test_settings_accepts_supported_database_url() -> None:
	settings = BootSettings(DATABASE_URL="postgresql://user@localhost/db")
	assert settings.DATABASE_URL.startswith("postgresql://")


def test_psycopg_event_loop_policy_noop_off_windows(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Policy helper should be a no-op when not on Windows."""

	called = False

	def _mark_called(_policy: object) -> None:
		nonlocal called
		called = True

	# Create a fake sys module with linux platform
	fake_sys = types.ModuleType("fake_sys")
	fake_sys.platform = "linux"  # type: ignore[attr-defined]

	monkeypatch.setattr(runtime_module, "sys", fake_sys)
	monkeypatch.setattr(runtime_module, "asyncio", database_module.asyncio)
	monkeypatch.setattr(runtime_module.asyncio, "set_event_loop_policy", _mark_called)
	# Call helper again under a non-windows platform
	config_module.configure_psycopg_asyncio_event_loop_policy()
	assert called is False


@pytest.mark.asyncio
async def test_get_db_commits_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
	session = _DummySession()
	monkeypatch.setattr(
		database_module,
		"AsyncSessionLocal",
		lambda: _DummySessionContext(session),
	)

	generator = database_module.get_db()
	yielded_session = await generator.__anext__()
	assert yielded_session is session

	with pytest.raises(StopAsyncIteration):
		await generator.asend(None)

	assert session.committed is True
	assert session.closed is True


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
	session = _DummySession()
	monkeypatch.setattr(
		database_module,
		"AsyncSessionLocal",
		lambda: _DummySessionContext(session),
	)

	generator = database_module.get_db()
	await generator.__anext__()
	with pytest.raises(RuntimeError):
		await generator.athrow(RuntimeError("boom"))

	assert session.rolled_back is True
	assert session.closed is True


@pytest.mark.asyncio
async def test_init_db_runs_alembic_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
	"""Test that init_db runs alembic upgrade head."""
	mock_upgrade = MagicMock()
	monkeypatch.setattr(database_module.command, "upgrade", mock_upgrade)

	await database_module.init_db()

	mock_upgrade.assert_called_once()
	args, _ = mock_upgrade.call_args
	assert isinstance(args[0], database_module.Config)
	assert args[1] == "head"


@pytest.mark.asyncio
async def test_init_db_runs_alembic_upgrade_heads_when_branching_enabled(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""init_db should run alembic upgrade heads when branching is enabled."""
	mock_upgrade = MagicMock()
	monkeypatch.setattr(database_module.command, "upgrade", mock_upgrade)

	class MockBootSettings:
		DATABASE_URL = database_module.boot_settings.DATABASE_URL
		DEBUG = False
		BRANCHING_MIGRATIONS = True

	monkeypatch.setattr(database_module, "boot_settings", MockBootSettings())

	await database_module.init_db()

	mock_upgrade.assert_called_once()
	args, _ = mock_upgrade.call_args
	assert isinstance(args[0], database_module.Config)
	assert args[1] == "heads"


@pytest.mark.asyncio
async def test_init_db_masks_url_credentials(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""Test that init_db masks credentials in URLs containing @ symbol."""
	caplog.set_level(logging.INFO, logger=database_module.logger.name)

	# Mock alembic command to avoid actual DB operations
	mock_upgrade = MagicMock()
	monkeypatch.setattr(database_module.command, "upgrade", mock_upgrade)

	# mock settings with a URL that has credentials (contains @)
	class MockBootSettings:
		DATABASE_URL = "postgresql://user:secret@localhost:5432/db"
		DEBUG = False
		BRANCHING_MIGRATIONS = False

	monkeypatch.setattr(database_module, "boot_settings", MockBootSettings())

	await database_module.init_db()

	# Verify the log message contains the masked URL
	assert "initializing database" in caplog.text
	# The extra dict is not directly in caplog.text usually,
	# but the formatter might put it there.
	# However, we can check the records.
	assert len(caplog.records) > 0
	record = caplog.records[0]
	assert record.message == "initializing database"
	assert getattr(record, "url", None) == "postgresql://***@localhost:5432/db"


@pytest.mark.asyncio
async def test_init_db_logs_plain_url_when_no_credentials(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""init_db should log the URL unchanged when it contains no credentials."""
	caplog.set_level(logging.INFO, logger=database_module.logger.name)

	mock_upgrade = MagicMock()
	monkeypatch.setattr(database_module.command, "upgrade", mock_upgrade)

	class MockBootSettings:
		DATABASE_URL = "postgresql://localhost:5432/db"
		DEBUG = False
		BRANCHING_MIGRATIONS = False

	monkeypatch.setattr(database_module, "boot_settings", MockBootSettings())

	await database_module.init_db()

	assert "initializing database" in caplog.text
	record = caplog.records[0]
	assert record.message == "initializing database"
	assert getattr(record, "url", None) == "postgresql://localhost:5432/db"


@pytest.mark.asyncio
async def test_init_db_handles_migration_error(
	monkeypatch: pytest.MonkeyPatch,
	caplog: pytest.LogCaptureFixture,
) -> None:
	"""Test that init_db logs and re-raises errors during migration."""
	mock_upgrade = MagicMock(side_effect=RuntimeError("migration failed"))
	monkeypatch.setattr(database_module.command, "upgrade", mock_upgrade)
	monkeypatch.setattr(database_module, "_build_alembic_config", lambda: MagicMock())

	with pytest.raises(RuntimeError, match="migration failed"):
		await database_module.init_db()

	assert "error running migrations: migration failed" in caplog.text


@pytest.mark.asyncio
async def test_get_db_rolls_back_on_commit_error(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Test that get_db rolls back if commit fails."""
	session = _DummySession()

	# Make commit raise an error
	async def mock_commit() -> None:
		raise RuntimeError("commit failed")

	session.commit = mock_commit  # type: ignore

	monkeypatch.setattr(
		database_module,
		"AsyncSessionLocal",
		lambda: _DummySessionContext(session),
	)

	generator = database_module.get_db()
	await generator.__anext__()

	# Finish the generator normally, which triggers commit()
	with pytest.raises(RuntimeError, match="commit failed"):
		try:
			await generator.__anext__()
		except StopAsyncIteration:
			pass

	assert session.rolled_back is True
	assert session.closed is True
