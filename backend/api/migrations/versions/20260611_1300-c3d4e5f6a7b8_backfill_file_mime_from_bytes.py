"""backfill file mime_type from content bytes

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-11 13:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


async def _read_header(backend_name: str, key: str, limit: int = 4096) -> bytes:
	"""read up to limit leading bytes of a stored object."""
	from api.storage import get_storage_backend

	backend = get_storage_backend(backend_name)
	stream = await backend.get(key)
	buf = bytearray()
	async for chunk in stream:
		buf.extend(chunk)
		if len(buf) >= limit:
			break
	return bytes(buf[:limit])


def upgrade() -> None:
	"""correct stored mime_type values that disagree with the actual bytes.

	historical uploads trusted the client-supplied content type, which can
	lie (e.g. a jpeg labeled image/png) and break downstream model APIs.
	this re-sniffs each file's content and applies the same authoritative
	correction now enforced at write time. best-effort: unreadable objects
	are skipped so the migration never fails on storage errors.
	"""
	from sqlalchemy.util import await_only

	from api.storage import close_all, configure_storage_backends
	from nokodo_ai.utils.files import corrected_mime_type

	bind = op.get_bind()
	await_only(configure_storage_backends())
	try:
		rows = (
			bind.execute(
				sa.text(
					"SELECT id, storage_backend, storage_key, mime_type "
					"FROM files WHERE deleted_at IS NULL"
				)
			)
			.mappings()
			.all()
		)
		for row in rows:
			try:
				header = await_only(
					_read_header(row["storage_backend"], row["storage_key"])
				)
			except Exception:
				continue
			corrected = corrected_mime_type(row["mime_type"], header)
			if corrected and corrected != row["mime_type"]:
				bind.execute(
					sa.text("UPDATE files SET mime_type = :mime WHERE id = :id"),
					{"mime": corrected, "id": row["id"]},
				)
	finally:
		await_only(close_all())


def downgrade() -> None:
	"""no-op: the original (incorrect) mime types are not recoverable."""
	pass
