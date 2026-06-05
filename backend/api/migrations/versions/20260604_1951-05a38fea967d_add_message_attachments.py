"""add attachments column to messages

Revision ID: 05a38fea967d
Revises: c9d8e7f6a5b4
Create Date: 2026-06-04 19:51:13.346942
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "05a38fea967d"
down_revision = "c9d8e7f6a5b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column(
		"messages",
		sa.Column("attachments", JSONB, nullable=False, server_default="[]"),
	)


def downgrade() -> None:
	op.drop_column("messages", "attachments")
