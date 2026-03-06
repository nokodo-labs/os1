"""drop agent visibility column

Revision ID: a1b2c3d4e5f6
Revises: 4a9e3a556baf
Create Date: 2026-02-10 01:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "4a9e3a556baf"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.drop_column("agents", "visibility")


def downgrade() -> None:
	op.add_column(
		"agents",
		sa.Column(
			"visibility",
			sa.String(length=20),
			server_default="public",
			nullable=False,
		),
	)
