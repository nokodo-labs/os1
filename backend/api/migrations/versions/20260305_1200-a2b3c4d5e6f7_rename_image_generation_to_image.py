"""rename model_type image_generation to image

Revision ID: a2b3c4d5e6f7
Revises: f7a1b5c9d2e8
Create Date: 2026-03-05 12:00:00.000000
"""

from alembic import op


revision = "a2b3c4d5e6f7"
down_revision = "f7a1b5c9d2e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute(
		"UPDATE models SET model_type = 'image' WHERE model_type = 'image_generation'"
	)


def downgrade() -> None:
	op.execute(
		"UPDATE models SET model_type = 'image_generation' WHERE model_type = 'image'"
	)
