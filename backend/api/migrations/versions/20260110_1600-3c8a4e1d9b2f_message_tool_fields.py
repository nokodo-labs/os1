"""add native tool fields to messages.

Revision ID: 3c8a4e1d9b2f
Revises: 0b7c2d9f4a1e
Create Date: 2026-01-10 16:00:00

"""

import sqlalchemy as sa
from alembic import op


revision = "3c8a4e1d9b2f"
down_revision = "0b7c2d9f4a1e"
branch_labels = None
depends_on = None


TYPEID_LENGTH = 90


def upgrade() -> None:
	op.add_column(
		"messages",
		sa.Column("tool_call_id", sa.String(length=TYPEID_LENGTH), nullable=True),
	)
	op.add_column("messages", sa.Column("is_error", sa.Boolean(), nullable=True))
	op.create_index(
		"ix_messages_tool_call_id",
		"messages",
		["tool_call_id"],
		unique=False,
	)

	# backfill from metadata json and remove keys
	op.execute(
		"""
		UPDATE messages
		SET
			tool_call_id = NULLIF(metadata::jsonb->>'tool_call_id', ''),
			is_error = CASE
				WHEN lower(metadata::jsonb->>'is_error') IN ('true','false')
					THEN (metadata::jsonb->>'is_error')::boolean
				ELSE NULL
			END,
			metadata = (
				(metadata::jsonb - 'tool_call_id' - 'is_error')
			)::json
		WHERE type = 'tool'
		"""
	)


def downgrade() -> None:
	# re-add keys into metadata for tool messages
	op.execute(
		"""
		UPDATE messages
		SET metadata = (
			(
				metadata::jsonb
				|| CASE
					WHEN tool_call_id IS NOT NULL THEN jsonb_build_object(
						'tool_call_id',
						tool_call_id
					)
					ELSE '{}'::jsonb
				END
				|| CASE
					WHEN is_error IS NOT NULL THEN jsonb_build_object(
						'is_error',
						is_error
					)
					ELSE '{}'::jsonb
				END
			)
		)::json
		WHERE type = 'tool'
		"""
	)

	op.drop_index("ix_messages_tool_call_id", table_name="messages")
	op.drop_column("messages", "is_error")
	op.drop_column("messages", "tool_call_id")
