"""add settings_documents table.

Revision ID: 9b1f2c3d4e5a
Revises: 3c8a4e1d9b2f
Create Date: 2026-01-17 01:40:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "9b1f2c3d4e5a"
down_revision = "3c8a4e1d9b2f"
branch_labels = None
depends_on = None


TYPEID_LENGTH = 90


def upgrade() -> None:
	op.create_table(
		"settings_documents",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column(
			"updated_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.Column("namespace", sa.String(length=100), nullable=False),
		sa.Column("data", postgresql.JSONB(), nullable=False),
		sa.Column("version", sa.Integer(), nullable=False),
		sa.Column("updated_by_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index(
		"ix_settings_documents_namespace",
		"settings_documents",
		["namespace"],
		unique=True,
	)


def downgrade() -> None:
	op.drop_index("ix_settings_documents_namespace", table_name="settings_documents")
	op.drop_table("settings_documents")
