"""transaction-scoped PostgreSQL advisory locks."""

import hashlib

from fastapi import HTTPException, status
from psycopg.errors import DeadlockDetected, LockNotAvailable
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from nokodo_ai.utils.typeid import TypeID


RESOURCE_WRITE_LOCK_TIMEOUT_MS = 5000
"""how long a resource write waits for its transaction lock."""


def _resource_lock_key(namespace: str, resource_id: TypeID) -> int:
	digest = hashlib.sha256(f"{namespace}:{resource_id}".encode()).digest()
	return int.from_bytes(digest[:8], "big", signed=True)


async def acquire_resource_write_lock(
	session: AsyncSession,
	namespace: str,
	resource_id: TypeID,
) -> None:
	"""serialize writes to one resource across processes."""
	await session.execute(
		text(f"SET LOCAL lock_timeout = '{RESOURCE_WRITE_LOCK_TIMEOUT_MS}ms'")
	)
	try:
		await session.execute(
			select(
				func.pg_advisory_xact_lock(_resource_lock_key(namespace, resource_id))
			)
		)
	except DBAPIError as exc:
		if not isinstance(exc.orig, LockNotAvailable | DeadlockDetected):
			raise
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail=f"{namespace} is busy; please retry",
		) from exc
