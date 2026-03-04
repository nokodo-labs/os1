"""add thread_summaries table

Revision ID: f7a1b5c9d2e8
Revises: e6f0a4b8c3d7
Create Date: 2026-03-02 18:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.models.base import TYPEID_LENGTH


revision = "f7a1b5c9d2e8"
down_revision = "e6f0a4b8c3d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.create_table(
		"thread_summaries",
		sa.Column(
			"id",
			sa.String(TYPEID_LENGTH),
			primary_key=True,
		),
		sa.Column(
			"thread_id",
			sa.String(TYPEID_LENGTH),
			sa.ForeignKey("threads.id", ondelete="CASCADE"),
			nullable=False,
			index=True,
		),
		sa.Column(
			"type",
			sa.String(20),
			nullable=False,
			server_default="window",
		),
		sa.Column(
			"start_message_id",
			sa.String(TYPEID_LENGTH),
			sa.ForeignKey("messages.id", ondelete="SET NULL"),
			nullable=True,
		),
		sa.Column(
			"end_message_id",
			sa.String(TYPEID_LENGTH),
			sa.ForeignKey("messages.id", ondelete="SET NULL"),
			nullable=True,
		),
		sa.Column(
			"message_count",
			sa.Integer,
			nullable=False,
			server_default="0",
		),
		sa.Column(
			"content",
			sa.Text,
			nullable=False,
			server_default="",
		),
		sa.Column(
			"superseded_by_id",
			sa.String(TYPEID_LENGTH),
			sa.ForeignKey("thread_summaries.id", ondelete="SET NULL"),
			nullable=True,
		),
		sa.Column(
			"metadata",
			JSONB,
			nullable=False,
			server_default="{}",
		),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.func.now(),
			nullable=False,
		),
		sa.Column(
			"updated_at",
			sa.DateTime(timezone=True),
			server_default=sa.func.now(),
			nullable=False,
		),
	)


def downgrade() -> None:
	op.drop_table("thread_summaries")
