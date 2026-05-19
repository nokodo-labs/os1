"""add resource search indexes

Revision ID: d6b7faed3314
Revises: 6e1b4a9d0c2f
Create Date: 2026-05-19 03:00:10.096178

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d6b7faed3314"
down_revision = "6e1b4a9d0c2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
	with op.batch_alter_table("calendar_events", schema=None) as batch_op:
		batch_op.create_index(
			"idx_calendar_events_location_trgm",
			["location"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"location": "gin_trgm_ops"},
		)

		batch_op.create_index(
			"idx_calendar_events_virtual_url_trgm",
			["virtual_url"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"virtual_url": "gin_trgm_ops"},
		)

	with op.batch_alter_table("files", schema=None) as batch_op:
		batch_op.create_index(
			"idx_files_description_trgm",
			["description"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"description": "gin_trgm_ops"},
		)
		batch_op.create_index(
			"idx_files_filename_trgm",
			["filename"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"filename": "gin_trgm_ops"},
		)


def downgrade() -> None:
	with op.batch_alter_table("files", schema=None) as batch_op:
		batch_op.drop_index(
			"idx_files_filename_trgm",
			postgresql_using="gin",
			postgresql_ops={"filename": "gin_trgm_ops"},
		)
		batch_op.drop_index(
			"idx_files_description_trgm",
			postgresql_using="gin",
			postgresql_ops={"description": "gin_trgm_ops"},
		)

	with op.batch_alter_table("calendar_events", schema=None) as batch_op:
		batch_op.drop_index(
			"idx_calendar_events_virtual_url_trgm",
			postgresql_using="gin",
			postgresql_ops={"virtual_url": "gin_trgm_ops"},
		)
		batch_op.drop_index(
			"idx_calendar_events_location_trgm",
			postgresql_using="gin",
			postgresql_ops={"location": "gin_trgm_ops"},
		)
