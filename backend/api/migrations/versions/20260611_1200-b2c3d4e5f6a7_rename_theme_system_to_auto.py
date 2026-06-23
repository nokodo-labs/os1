"""rename theme mode 'system' to 'auto'

Revision ID: b2c3d4e5f6a7
Revises: 1d0f6efb111d
Create Date: 2026-06-11 12:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6a7"
down_revision = "1d0f6efb111d"
branch_labels = None
depends_on = None


def upgrade() -> None:
	"""migrate stored theme mode 'system' -> 'auto'."""
	op.execute(
		"""
		UPDATE users
		SET preferences = jsonb_set(
			preferences,
			'{appearance,themeMode}',
			'"auto"'::jsonb,
			true
		)
		WHERE preferences #>> '{appearance,themeMode}' = 'system';
		"""
	)
	op.execute(
		"""
		UPDATE settings_documents
		SET data = jsonb_set(
			data,
			'{default_theme}',
			'"auto"'::jsonb,
			true
		)
		WHERE namespace = 'ui'
		AND data #>> '{default_theme}' = 'system';
		"""
	)


def downgrade() -> None:
	"""revert theme mode 'auto' -> 'system'."""
	op.execute(
		"""
		UPDATE users
		SET preferences = jsonb_set(
			preferences,
			'{appearance,themeMode}',
			'"system"'::jsonb,
			true
		)
		WHERE preferences #>> '{appearance,themeMode}' = 'auto';
		"""
	)
	op.execute(
		"""
		UPDATE settings_documents
		SET data = jsonb_set(
			data,
			'{default_theme}',
			'"system"'::jsonb,
			true
		)
		WHERE namespace = 'ui'
		AND data #>> '{default_theme}' = 'auto';
		"""
	)
