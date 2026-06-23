"""add notification payload and push subscriptions

Revision ID: 5d9a2c4e7f10
Revises: 4c8d6e2f9a1b
Create Date: 2026-05-16 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers
revision = "5d9a2c4e7f10"
down_revision = "4c8d6e2f9a1b"
branch_labels = None
depends_on = None

TYPEID_LENGTH = 90


def upgrade() -> None:
	"""Apply notification payload and push subscription storage changes."""
	_add_notification_payload_fields()
	_create_user_client_table()
	_create_push_subscription_table()


def downgrade() -> None:
	"""Undo notification payload and push subscription storage changes."""
	_drop_push_subscription_table()
	_drop_user_client_table()
	_drop_notification_payload_fields()


def _add_notification_payload_fields() -> None:
	"""Add durable display payload columns to notifications."""
	with op.batch_alter_table("notifications", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column(
				"title",
				sa.String(length=200),
				nullable=False,
				server_default="notification",
			)
		)
		batch_op.add_column(sa.Column("body", sa.Text(), nullable=True))
		batch_op.add_column(sa.Column("icon_url", sa.Text(), nullable=True))
		batch_op.add_column(sa.Column("image_url", sa.Text(), nullable=True))
		batch_op.add_column(sa.Column("badge_url", sa.Text(), nullable=True))
		batch_op.add_column(sa.Column("action_url", sa.Text(), nullable=True))
		batch_op.add_column(sa.Column("tag", sa.String(length=128), nullable=True))
		batch_op.add_column(
			sa.Column(
				"data",
				postgresql.JSONB(astext_type=sa.Text()),
				nullable=False,
				server_default=sa.text("'{}'::jsonb"),
			)
		)
		batch_op.add_column(
			sa.Column(
				"actions",
				postgresql.JSONB(astext_type=sa.Text()),
				nullable=False,
				server_default=sa.text("'[]'::jsonb"),
			)
		)
		batch_op.add_column(
			sa.Column("require_interaction", sa.Boolean(), nullable=True)
		)
		batch_op.add_column(sa.Column("silent", sa.Boolean(), nullable=True))
		batch_op.add_column(sa.Column("renotify", sa.Boolean(), nullable=True))
		batch_op.add_column(
			sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
		)
	op.create_index(
		"ix_notifications_expires_at",
		"notifications",
		["expires_at"],
		unique=False,
	)

	op.execute(
		"""
		UPDATE notifications AS notification
		SET
			title = COALESCE(
				NULLIF(event.data ->> 'title', ''),
				event.type,
				'notification'
			),
			body = NULLIF(event.data ->> 'body', ''),
			icon_url = NULLIF(event.data ->> 'icon_url', ''),
			image_url = NULLIF(event.data ->> 'image_url', ''),
			badge_url = NULLIF(event.data ->> 'badge_url', ''),
			action_url = NULLIF(event.data ->> 'action_url', ''),
			tag = NULLIF(event.data ->> 'tag', ''),
			data = COALESCE(event.data - ARRAY[
				'title',
				'body',
				'icon_url',
				'image_url',
				'badge_url',
				'action_url',
				'tag',
				'actions',
				'require_interaction',
				'silent',
				'renotify'
			], '{}'::jsonb),
			actions = CASE
				WHEN jsonb_typeof(event.data -> 'actions') = 'array'
				THEN event.data -> 'actions'
				ELSE '[]'::jsonb
			END,
			require_interaction = CASE
				WHEN jsonb_typeof(event.data -> 'require_interaction') = 'boolean'
				THEN (event.data ->> 'require_interaction')::boolean
				ELSE NULL
			END,
			silent = CASE
				WHEN jsonb_typeof(event.data -> 'silent') = 'boolean'
				THEN (event.data ->> 'silent')::boolean
				ELSE NULL
			END,
			renotify = CASE
				WHEN jsonb_typeof(event.data -> 'renotify') = 'boolean'
				THEN (event.data ->> 'renotify')::boolean
				ELSE NULL
			END
		FROM events AS event
		WHERE notification.event_id = event.id
		"""
	)

	with op.batch_alter_table("notifications", schema=None) as batch_op:
		batch_op.alter_column("title", server_default=None)
		batch_op.alter_column("data", server_default=None)
		batch_op.alter_column("actions", server_default=None)


def _create_user_client_table() -> None:
	"""Create stable per-user client registry."""
	op.create_table(
		"user_clients",
		sa.Column("user_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("client_key", sa.String(length=128), nullable=False),
		sa.Column("name", sa.String(length=120), nullable=True),
		sa.Column("user_agent", sa.Text(), nullable=True),
		sa.Column(
			"info",
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
			server_default=sa.text("'{}'::jsonb"),
		),
		sa.Column(
			"preferences",
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
			server_default=sa.text("'{}'::jsonb"),
		),
		sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column(
			"updated_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("user_id", "client_key", name="uq_user_clients_user_key"),
	)
	op.create_index("ix_user_clients_user_id", "user_clients", ["user_id"])


def _create_push_subscription_table() -> None:
	"""Create web push subscription storage."""
	op.create_table(
		"notification_push_subscriptions",
		sa.Column("client_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("endpoint", sa.Text(), nullable=False),
		sa.Column("p256dh", sa.Text(), nullable=False),
		sa.Column("auth", sa.Text(), nullable=False),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column(
			"created_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column(
			"updated_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.ForeignKeyConstraint(["client_id"], ["user_clients.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint(
			"endpoint",
			name="uq_notification_push_subscriptions_endpoint",
		),
	)
	op.create_index(
		"ix_notification_push_subscriptions_client_id",
		"notification_push_subscriptions",
		["client_id"],
		unique=False,
	)


def _drop_push_subscription_table() -> None:
	"""Drop web push subscription storage."""
	op.drop_index(
		"ix_notification_push_subscriptions_client_id",
		table_name="notification_push_subscriptions",
	)
	op.drop_table("notification_push_subscriptions")


def _drop_user_client_table() -> None:
	"""Drop stable per-user client registry."""
	op.drop_index("ix_user_clients_user_id", table_name="user_clients")
	op.drop_table("user_clients")


def _drop_notification_payload_fields() -> None:
	"""Drop durable display payload columns from notifications."""
	op.drop_index("ix_notifications_expires_at", table_name="notifications")
	with op.batch_alter_table("notifications", schema=None) as batch_op:
		batch_op.drop_column("expires_at")
		batch_op.drop_column("renotify")
		batch_op.drop_column("silent")
		batch_op.drop_column("require_interaction")
		batch_op.drop_column("actions")
		batch_op.drop_column("data")
		batch_op.drop_column("tag")
		batch_op.drop_column("action_url")
		batch_op.drop_column("badge_url")
		batch_op.drop_column("image_url")
		batch_op.drop_column("icon_url")
		batch_op.drop_column("body")
		batch_op.drop_column("title")
