"""add username, find_by_email, privacy, bio columns to users

Revision ID: c4d8e2f6a1b3
Revises: b3e7f1a2c4d6
Create Date: 2026-02-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = "c4d8e2f6a1b3"
down_revision = "b3e7f1a2c4d6"
branch_labels = None
depends_on = None


JSON_TO_JSONB_COLUMNS: tuple[tuple[str, str], ...] = (
	("users", "preferences"),
	("users", "integration_tokens"),
	("users", "usage_quotas"),
	("access_rules", "metadata"),
	("agents", "metadata"),
	("agents", "plugin_ids"),
	("agents", "config"),
	("events", "metadata"),
	("events", "data"),
	("files", "metadata"),
	("group_memberships", "metadata"),
	("groups", "metadata"),
	("memories", "metadata"),
	("messages", "metadata"),
	("messages", "content"),
	("messages", "tool_calls"),
	("messages", "usage"),
	("messages", "read_by"),
	("models", "metadata"),
	("models", "capabilities"),
	("notes", "metadata"),
	("plugins", "metadata"),
	("projects", "metadata"),
	("prompts", "metadata"),
	("providers", "metadata"),
	("providers", "additional_headers"),
	("reminder_lists", "metadata"),
	("reminders", "metadata"),
	("roles", "metadata"),
	("roles", "quotas"),
	("roles", "default_permissions"),
	("settings_documents", "metadata"),
	("tasks", "metadata"),
	("tasks", "result"),
	("thread_participants", "metadata"),
	("threads", "metadata"),
	("threads", "tags"),
)


def upgrade() -> None:
	op.add_column(
		"users",
		sa.Column(
			"username",
			sa.String(length=40),
			nullable=True,
			unique=True,
		),
	)
	op.execute(
		"""
		WITH normalized AS (
			SELECT
				id,
				CASE
					WHEN clean = '' THEN 'user'
					WHEN char_length(clean) = 1 THEN clean || '00'
					WHEN char_length(clean) = 2 THEN clean || '0'
					WHEN char_length(clean) > 30 THEN left(clean, 30)
					ELSE clean
				END AS base_username
			FROM (
				SELECT
					id,
					regexp_replace(
						regexp_replace(
							regexp_replace(
								lower(split_part(email, '@', 1)),
								'[^a-z0-9._]+',
								'',
								'g'
							),
							'\\.{2,}',
							'.',
							'g'
						),
						'^[._]+|[._]+$',
						'',
						'g'
					) AS clean
				FROM users
			) base
		),
		ranked AS (
			SELECT
				id,
				base_username,
				row_number() OVER (PARTITION BY base_username ORDER BY id) AS rn
			FROM normalized
		),
		resolved AS (
			SELECT
				id,
				CASE
					WHEN rn = 1 THEN base_username
					ELSE
						left(base_username, greatest(1, 30 - length((rn - 1)::text)))
						|| (rn - 1)::text
				END AS username
			FROM ranked
		)
		UPDATE users u
		SET username = resolved.username
		FROM resolved
		WHERE u.id = resolved.id
		AND (u.username IS NULL OR u.username = '');
		"""
	)
	op.alter_column(
		"users",
		"username",
		existing_type=sa.String(length=40),
		nullable=False,
	)
	op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

	op.add_column(
		"users",
		sa.Column(
			"find_by_email",
			sa.Boolean(),
			nullable=False,
			server_default=sa.text("true"),
		),
	)
	op.create_index(
		op.f("ix_users_find_by_email"), "users", ["find_by_email"], unique=False
	)

	op.add_column(
		"users",
		sa.Column(
			"privacy",
			JSONB(),
			nullable=False,
			server_default=sa.text("'{}'::jsonb"),
		),
	)

	op.add_column(
		"users",
		sa.Column("bio", sa.String(length=500), nullable=True),
	)

	for table_name, column_name in JSON_TO_JSONB_COLUMNS:
		op.alter_column(
			table_name,
			column_name,
			type_=JSONB(),
			existing_type=sa.JSON(),
			postgresql_using=f"{column_name}::jsonb",
		)


def downgrade() -> None:
	for table_name, column_name in reversed(JSON_TO_JSONB_COLUMNS):
		op.alter_column(
			table_name,
			column_name,
			type_=sa.JSON(),
			existing_type=JSONB(),
			postgresql_using=f"{column_name}::json",
		)
	op.drop_column("users", "bio")
	op.drop_column("users", "privacy")
	op.drop_index(op.f("ix_users_find_by_email"), table_name="users")
	op.drop_column("users", "find_by_email")
	op.drop_index(op.f("ix_users_username"), table_name="users")
	op.drop_column("users", "username")
