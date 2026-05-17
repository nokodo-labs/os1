"""add project search indexes

Revision ID: 4c8d6e2f9a1b
Revises: 3b9740357ed8
Create Date: 2026-05-07 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "4c8d6e2f9a1b"
down_revision = "3b9740357ed8"
branch_labels = None
depends_on = None


def upgrade() -> None:
	with op.get_context().autocommit_block():
		op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_name_trgm "
			"ON projects USING GIN(name gin_trgm_ops)"
		)
		op.execute(
			"CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_projects_description_trgm "
			"ON projects USING GIN(description gin_trgm_ops)"
		)


def downgrade() -> None:
	with op.get_context().autocommit_block():
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_projects_description_trgm")
		op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_projects_name_trgm")
