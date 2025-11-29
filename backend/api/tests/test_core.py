"""Tests for configuration validators and database helpers."""

from __future__ import annotations

import pytest

from api.core import database as database_module
from api.core.config import Settings


class _DummySession:
	"""Lightweight async session stand-in for exercising get_db."""

	def __init__(self) -> None:
		self.committed = False
		self.rolled_back = False
		self.closed = False

	async def commit(self) -> None:  # pragma: no cover - exercised via get_db
		self.committed = True

	async def rollback(self) -> None:  # pragma: no cover - exercised via get_db
		self.rolled_back = True

	async def close(self) -> None:  # pragma: no cover - exercised via get_db
		self.closed = True


class _DummySessionContext:
	"""Provides the async context manager protocol used by AsyncSession."""

	def __init__(self, session: _DummySession) -> None:
		self._session = session
		self.exited = False

	async def __aenter__(self) -> _DummySession:
		return self._session

	async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - trivial
		self.exited = True


class _DummyConnection:
	def __init__(self) -> None:
		self.called_with = None

	async def run_sync(self, fn):
		self.called_with = fn


class _DummyEngine:
	def __init__(self, connection: _DummyConnection) -> None:
		self._connection = connection

	def begin(self):
		connection = self._connection

		class _BeginContext:
			async def __aenter__(self):
				return connection

			async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover
				return False

		return _BeginContext()


def test_settings_parse_cors_origins_from_string() -> None:
	settings = Settings(CORS_ORIGINS="https://a.com, https://b.com")
	assert settings.CORS_ORIGINS == ["https://a.com", "https://b.com"]


def test_settings_validate_database_url_scheme() -> None:
	with pytest.raises(ValueError):
		Settings(DATABASE_URL="mysql://localhost/db")


def test_settings_accepts_supported_database_url() -> None:
	settings = Settings(DATABASE_URL="postgresql://user@localhost/db")
	assert settings.DATABASE_URL.startswith("postgresql://")


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
async def test_init_db_runs_create_all(monkeypatch: pytest.MonkeyPatch) -> None:
	connection = _DummyConnection()
	dummy_engine = _DummyEngine(connection)
	monkeypatch.setattr(database_module, "engine", dummy_engine)

	await database_module.init_db()

	called = connection.called_with
	assert callable(called)
	assert getattr(called, "__self__", None) is database_module.Base.metadata
	assert getattr(called, "__name__", "") == "create_all"
