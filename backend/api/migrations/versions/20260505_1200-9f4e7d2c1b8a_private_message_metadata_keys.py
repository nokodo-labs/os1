"""private message metadata keys

Revision ID: 9f4e7d2c1b8a
Revises: f3a4b5c6d7e8
Create Date: 2026-05-05 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "9f4e7d2c1b8a"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


KEY_RENAMES = (
	("message_id", "_message_id"),
	("created_at", "_created_at"),
	("next_citation_index", "_next_citation_index"),
	("citations", "_citations"),
	("e2b_sandbox_id", "_e2b_sandbox_id"),
	("citable_sources", "_citable_sources"),
)


def upgrade() -> None:
	"""move runtime-only message metadata behind private keys."""
	for old_key, new_key in KEY_RENAMES:
		_rename_metadata_key(old_key, new_key)


def downgrade() -> None:
	"""restore the previous public metadata key names."""
	for old_key, new_key in reversed(KEY_RENAMES):
		_rename_metadata_key(new_key, old_key)


def _rename_metadata_key(old_key: str, new_key: str) -> None:
	"""rename one top-level JSONB key on message metadata."""
	op.execute(
		sa.text(
			"""
			UPDATE messages
			SET "metadata" = CASE
				WHEN "metadata" ? :new_key THEN "metadata" - :old_key
				ELSE jsonb_set(
					"metadata",
					ARRAY[:new_key]::text[],
					"metadata" -> :old_key,
					true
				) - :old_key
			END
			WHERE "metadata" ? :old_key
			"""
		).bindparams(old_key=old_key, new_key=new_key)
	)
