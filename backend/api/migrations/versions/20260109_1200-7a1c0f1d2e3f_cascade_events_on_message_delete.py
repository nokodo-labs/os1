"""cascade events on message delete.

Revision ID: 7a1c0f1d2e3f
Revises: c76fff12fadc
Create Date: 2026-01-09 12:00:00

"""

from alembic import op


revision = "7a1c0f1d2e3f"
down_revision = "c76fff12fadc"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.drop_constraint("events_message_id_fkey", "events", type_="foreignkey")
	op.create_foreign_key(
		"events_message_id_fkey",
		"events",
		"messages",
		["message_id"],
		["id"],
		ondelete="CASCADE",
	)


def downgrade() -> None:
	op.drop_constraint("events_message_id_fkey", "events", type_="foreignkey")
	op.create_foreign_key(
		"events_message_id_fkey",
		"events",
		"messages",
		["message_id"],
		["id"],
		ondelete="SET NULL",
	)
