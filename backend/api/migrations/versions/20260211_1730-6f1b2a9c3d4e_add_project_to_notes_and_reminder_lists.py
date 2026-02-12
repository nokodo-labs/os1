"""add_project_to_notes_and_reminder_lists

Revision ID: 6f1b2a9c3d4e
Revises: a1b2c3d4e5f6
Create Date: 2026-02-11 17:30:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "6f1b2a9c3d4e"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
	with op.batch_alter_table("notes", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column("project_id", sa.String(length=90), nullable=True)
		)
		batch_op.create_foreign_key(
			"notes_project_id_fkey",
			"projects",
			["project_id"],
			["id"],
			ondelete="SET NULL",
		)
		batch_op.create_index("ix_notes_project_id", ["project_id"])

	with op.batch_alter_table("reminder_lists", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column("project_id", sa.String(length=90), nullable=True)
		)
		batch_op.create_foreign_key(
			"reminder_lists_project_id_fkey",
			"projects",
			["project_id"],
			["id"],
			ondelete="SET NULL",
		)
		batch_op.create_index("ix_reminder_lists_project_id", ["project_id"])


def downgrade() -> None:
	with op.batch_alter_table("reminder_lists", schema=None) as batch_op:
		batch_op.drop_index("ix_reminder_lists_project_id")
		batch_op.drop_constraint("reminder_lists_project_id_fkey", type_="foreignkey")
		batch_op.drop_column("project_id")

	with op.batch_alter_table("notes", schema=None) as batch_op:
		batch_op.drop_index("ix_notes_project_id")
		batch_op.drop_constraint("notes_project_id_fkey", type_="foreignkey")
		batch_op.drop_column("project_id")
