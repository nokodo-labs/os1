"""Database configuration and session management."""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
	AsyncSession,
	async_sessionmaker,
	create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.core.config import settings


logger = logging.getLogger(__name__)


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
	"""Initialize database tables."""
	logger.info("initializing database at %s", settings.DATABASE_URL)
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)
	logger.info("database initialized successfully")
