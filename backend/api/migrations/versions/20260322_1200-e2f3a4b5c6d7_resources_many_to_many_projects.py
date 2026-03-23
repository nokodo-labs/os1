"""convert file/note/reminder_list project FK to many-to-many

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-22 12:00:00.000000

replaces the single project_id FK on files, notes, and reminder_lists
with junction tables (file_projects, note_projects, reminder_list_projects)
so each resource can belong to multiple projects simultaneously.

existing project_id values are migrated into the new association tables
before the columns are dropped.
"""

import sqlalchemy as sa
from alembic import op


# revision identifiers
revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

TYPEID_LENGTH = 90


def upgrade() -> None:
	# --- file_projects ---
	op.create_table(
		"file_projects",
		sa.Column("file_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("file_id", "project_id"),
	)

	# --- note_projects ---
	op.create_table(
		"note_projects",
		sa.Column("note_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("note_id", "project_id"),
	)

	# --- reminder_list_projects ---
	op.create_table(
		"reminder_list_projects",
		sa.Column("reminder_list_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.ForeignKeyConstraint(
			["reminder_list_id"], ["reminder_lists.id"], ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("reminder_list_id", "project_id"),
	)

	# migrate existing data - files
	op.execute(
		"""
		INSERT INTO file_projects (file_id, project_id)
		SELECT id, project_id FROM files WHERE project_id IS NOT NULL
		"""
	)

	# migrate existing data - notes
	op.execute(
		"""
		INSERT INTO note_projects (note_id, project_id)
		SELECT id, project_id FROM notes WHERE project_id IS NOT NULL
		"""
	)

	# migrate existing data - reminder_lists
	op.execute(
		"""
		INSERT INTO reminder_list_projects (reminder_list_id, project_id)
		SELECT id, project_id FROM reminder_lists WHERE project_id IS NOT NULL
		"""
	)

	# drop old FK columns
	op.drop_index("ix_files_project_id", table_name="files")
	op.drop_constraint("files_project_id_fkey", "files", type_="foreignkey")
	op.drop_column("files", "project_id")

	op.drop_index("ix_notes_project_id", table_name="notes")
	op.drop_constraint("notes_project_id_fkey", "notes", type_="foreignkey")
	op.drop_column("notes", "project_id")

	op.drop_index("ix_reminder_lists_project_id", table_name="reminder_lists")
	op.drop_constraint(
		"reminder_lists_project_id_fkey", "reminder_lists", type_="foreignkey"
	)
	op.drop_column("reminder_lists", "project_id")


def downgrade() -> None:
	# restore columns
	op.add_column(
		"files",
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=True),
	)
	op.create_foreign_key(
		"files_project_id_fkey",
		"files",
		"projects",
		["project_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_index("ix_files_project_id", "files", ["project_id"])

	op.add_column(
		"notes",
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=True),
	)
	op.create_foreign_key(
		"notes_project_id_fkey",
		"notes",
		"projects",
		["project_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_index("ix_notes_project_id", "notes", ["project_id"])

	op.add_column(
		"reminder_lists",
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=True),
	)
	op.create_foreign_key(
		"reminder_lists_project_id_fkey",
		"reminder_lists",
		"projects",
		["project_id"],
		["id"],
		ondelete="SET NULL",
	)
	op.create_index("ix_reminder_lists_project_id", "reminder_lists", ["project_id"])

	# restore data (only first project per resource, best-effort)
	op.execute(
		"""
		UPDATE files f SET project_id = fp.project_id
		FROM (SELECT DISTINCT ON (file_id) file_id, project_id FROM file_projects) fp
		WHERE f.id = fp.file_id
		"""
	)
	op.execute(
		"""
		UPDATE notes n SET project_id = np.project_id
		FROM (SELECT DISTINCT ON (note_id) note_id, project_id FROM note_projects) np
		WHERE n.id = np.note_id
		"""
	)
	op.execute(
		"""
		UPDATE reminder_lists rl SET project_id = rp.project_id
		FROM (
			SELECT DISTINCT ON (reminder_list_id) reminder_list_id, project_id
			FROM reminder_list_projects
		) rp
		WHERE rl.id = rp.reminder_list_id
		"""
	)

	# drop junction tables
	op.drop_table("reminder_list_projects")
	op.drop_table("note_projects")
	op.drop_table("file_projects")
