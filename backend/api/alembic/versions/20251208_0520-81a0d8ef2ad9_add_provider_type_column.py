"""add_provider_type_column

Revision ID: 81a0d8ef2ad9
Revises: 553e243baac5
Create Date: 2025-12-08 05:20:03.622819

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "81a0d8ef2ad9"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
	with op.batch_alter_table("providers") as batch_op:
		batch_op.add_column(
			sa.Column(
				"provider_type",
				sa.Enum("local", "external", name="provider_type_enum"),
				nullable=False,
				server_default="external",
			)
		)


def downgrade() -> None:
	with op.batch_alter_table("providers") as batch_op:
		batch_op.drop_column("provider_type")
