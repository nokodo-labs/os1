"""strip leading slashes from prompt commands

Revision ID: 8b2d4e6f7a9c
Revises: 6f1b2a9c3d4e
Create Date: 2026-02-20 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8b2d4e6f7a9c"
down_revision = "6f1b2a9c3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
	# strip the leading '/' from all prompt commands
	op.execute(
		"UPDATE prompts SET command = SUBSTRING(command FROM 2) WHERE command LIKE '/%'"
	)


def downgrade() -> None:
	# re-add the leading '/' to all prompt commands
	op.execute(
		"UPDATE prompts SET command = '/' || command WHERE command NOT LIKE '/%'"
	)
