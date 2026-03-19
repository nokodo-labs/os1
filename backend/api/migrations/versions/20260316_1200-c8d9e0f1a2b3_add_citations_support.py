"""add citations column to messages

Revision ID: c8d9e0f1a2b3
Revises: b4c5d6e7f8a9
Create Date: 2026-03-16 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "c8d9e0f1a2b3"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column(
		"messages",
		sa.Column("citations", JSONB, nullable=False, server_default="[]"),
	)


def downgrade() -> None:
	op.drop_column("messages", "citations")
