"""memory category to tags array

Revision ID: 3b9740357ed8
Revises: 9f4e7d2c1b8a
Create Date: 2026-05-06 03:24:35.568988

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "3b9740357ed8"
down_revision = "9f4e7d2c1b8a"
branch_labels = None
depends_on = None


def upgrade() -> None:
	# convert varchar(50) to varchar[] and rename to tags
	op.execute(
		"""
        ALTER TABLE memories
        ALTER COLUMN category TYPE varchar[]
        USING CASE WHEN category IS NOT NULL THEN ARRAY[category] ELSE NULL END
        """
	)
	op.alter_column("memories", "category", new_column_name="tags")


def downgrade() -> None:
	op.alter_column("memories", "tags", new_column_name="category")
	op.execute(
		"""
        ALTER TABLE memories
        ALTER COLUMN category TYPE varchar(50)
        USING CASE WHEN category IS NOT NULL THEN category[1] ELSE NULL END
        """
	)
