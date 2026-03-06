"""add pg_trgm extension and search indexes

Revision ID: 1a3b5c7d9e0f
Revises: 9ad4bb8aa7a0
Create Date: 2026-02-22 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "1a3b5c7d9e0f"
down_revision = "9ad4bb8aa7a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
	# enable pg_trgm extension (runs in its own transaction)
	with op.get_context().autocommit_block():
		op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

	# CREATE INDEX CONCURRENTLY cannot run inside a transaction block,
	# so each index is created in an autocommit block.
	with op.get_context().autocommit_block():
		# GIN trigram indexes for notes autocomplete
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_title_trgm "
			"ON notes USING GIN(title gin_trgm_ops)"
		)
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notes_content_trgm "
			"ON notes USING GIN(content gin_trgm_ops)"
		)

		# GIN trigram index for threads autocomplete
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_threads_title_trgm "
			"ON threads USING GIN(title gin_trgm_ops)"
		)

		# GIN trigram indexes for reminders autocomplete
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_title_trgm "
			"ON reminders USING GIN(title gin_trgm_ops)"
		)
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminders_description_trgm "
			"ON reminders USING GIN(description gin_trgm_ops)"
		)

		# GIN trigram index for reminder lists (searched via join)
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reminder_lists_name_trgm "
			"ON reminder_lists USING GIN(name gin_trgm_ops)"
		)

		# GIN trigram index for memories autocomplete
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_content_trgm "
			"ON memories USING GIN(content gin_trgm_ops)"
		)


def downgrade() -> None:
	with op.get_context().autocommit_block():
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_memories_content_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_reminder_lists_name_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_reminders_description_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_reminders_title_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_threads_title_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_notes_content_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_notes_title_trgm")
	op.execute("DROP EXTENSION IF EXISTS pg_trgm")
