"""drop provider model_prefix column

Revision ID: b4c5d6e7f8a9
Revises: a2b3c4d5e6f7
Create Date: 2026-03-06 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "b4c5d6e7f8a9"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.drop_column("providers", "model_prefix")


def downgrade() -> None:
	op.add_column(
		"providers",
		sa.Column("model_prefix", sa.String(50), nullable=True),
	)
