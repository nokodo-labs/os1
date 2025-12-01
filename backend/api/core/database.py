"""Database configuration and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.core.config import settings
from api.core.logging import get_logger


logger = get_logger(__name__)


class Base(DeclarativeBase):
	"""Base class for SQLAlchemy models."""

	pass


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


async def init_db() -> None:
	"""initialize database tables."""
	# mask credentials in url for logging
	db_url = str(settings.DATABASE_URL)
	if "@" in db_url:
		scheme_and_creds, host_and_db = db_url.rsplit("@", 1)
		scheme = scheme_and_creds.split("://")[0]
		safe_url = f"{scheme}://***@{host_and_db}"
	else:
		safe_url = db_url

	logger.info("initializing database", extra={"url": safe_url})
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
	logger.info("database initialized")
