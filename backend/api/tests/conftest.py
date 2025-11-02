"""Pytest configuration and fixtures."""

import asyncio
import sys
from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.core.config import settings
from api.core.database import Base


# Configure settings for tests before importing the app
settings.TESTING = True

# Test database URL (use a separate sqlite database for CI)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
	"""Create an instance of the default event loop for the test session."""
	# Use SelectorEventLoop on Windows for psycopg compatibility
	if sys.platform == "win32":
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	loop = asyncio.get_event_loop_policy().new_event_loop()
	yield loop
	loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
	"""Create a test database session."""
	# Create test engine
	engine = create_async_engine(TEST_DATABASE_URL, echo=True)

	# Create tables
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.drop_all)
		await conn.run_sync(Base.metadata.create_all)

	# Create session
	test_session_local = async_sessionmaker(
		engine,
		class_=AsyncSession,
		expire_on_commit=False,
		autocommit=False,
		autoflush=False,
	)

	async with test_session_local() as session:
		yield session

	# Cleanup
	await engine.dispose()


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
	"""Create a test client with overridden database dependency."""

	# Import after TESTING flag is set to avoid startup DB init
	from api.core.database import get_db
	from api.main import app

	async def override_get_db() -> AsyncGenerator[AsyncSession]:
		yield db_session

	app.dependency_overrides[get_db] = override_get_db

	async with AsyncClient(
		transport=ASGITransport(app=app), base_url="http://test"
	) as test_client:
		yield test_client

	app.dependency_overrides.clear()
