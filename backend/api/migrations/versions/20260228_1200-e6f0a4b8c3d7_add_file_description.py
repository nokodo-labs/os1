"""add description column to files table

Revision ID: e6f0a4b8c3d7
Revises: d5e9f3a7b2c4
Create Date: 2026-02-28 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "e6f0a4b8c3d7"
down_revision = "d5e9f3a7b2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column("files", sa.Column("description", sa.Text, nullable=True))


def downgrade() -> None:
	op.drop_column("files", "description")
