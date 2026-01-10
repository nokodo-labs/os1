"""add model adapter.

Revision ID: 0b7c2d9f4a1e
Revises: 7a1c0f1d2e3f
Create Date: 2026-01-10 13:15:00

"""

import sqlalchemy as sa
from alembic import op


revision = "0b7c2d9f4a1e"
down_revision = "7a1c0f1d2e3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column("models", sa.Column("adapter", sa.String(length=100), nullable=True))


def downgrade() -> None:
	op.drop_column("models", "adapter")
