"""drop redundant users_username_key unique constraint

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b3
Create Date: 2026-03-20 12:00:00.000000

The constraint was created implicitly by op.add_column(..., unique=True) in an
earlier migration. The model only declares ix_users_username (an explicit index),
so Alembic autogenerate sees users_username_key as drift. Drop it here so the
DB matches the model.
"""

from alembic import op


# revision identifiers
revision = "d1e2f3a4b5c6"
down_revision = "c8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.drop_constraint("users_username_key", "users", type_="unique")


def downgrade() -> None:
	op.create_unique_constraint("users_username_key", "users", ["username"])
