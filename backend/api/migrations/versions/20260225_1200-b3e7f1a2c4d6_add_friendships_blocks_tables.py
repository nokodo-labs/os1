"""add friendships, friendship_events, and blocks tables

Revision ID: b3e7f1a2c4d6
Revises: 1a3b5c7d9e0f
Create Date: 2026-02-25 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "b3e7f1a2c4d6"
down_revision = "1a3b5c7d9e0f"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.create_table(
		"friendships",
		sa.Column("requester_id", sa.String(length=90), nullable=False),
		sa.Column("addressee_id", sa.String(length=90), nullable=False),
		sa.Column(
			"status",
			sa.String(length=20),
			nullable=False,
			server_default="pending",
		),
		sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("id", sa.String(length=90), nullable=False),
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
		sa.ForeignKeyConstraint(
			["requester_id"],
			["users.id"],
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["addressee_id"],
			["users.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint(
			"requester_id",
			"addressee_id",
			name="uq_friendship_pair",
		),
	)
	with op.batch_alter_table("friendships", schema=None) as batch_op:
		batch_op.create_index(
			batch_op.f("ix_friendships_requester_id"),
			["requester_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_friendships_addressee_id"),
			["addressee_id"],
			unique=False,
		)

	op.create_table(
		"friendship_events",
		sa.Column("friendship_id", sa.String(length=90), nullable=False),
		sa.Column("status", sa.String(length=20), nullable=False),
		sa.Column("actor_id", sa.String(length=90), nullable=False),
		sa.Column("id", sa.String(length=90), nullable=False),
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
		sa.ForeignKeyConstraint(
			["friendship_id"],
			["friendships.id"],
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["actor_id"],
			["users.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
	)
	with op.batch_alter_table("friendship_events", schema=None) as batch_op:
		batch_op.create_index(
			batch_op.f("ix_friendship_events_friendship_id"),
			["friendship_id"],
			unique=False,
		)

	op.create_table(
		"blocks",
		sa.Column("blocker_id", sa.String(length=90), nullable=False),
		sa.Column("blocked_id", sa.String(length=90), nullable=False),
		sa.Column("id", sa.String(length=90), nullable=False),
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
		sa.ForeignKeyConstraint(
			["blocker_id"],
			["users.id"],
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["blocked_id"],
			["users.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint(
			"blocker_id",
			"blocked_id",
			name="uq_block_pair",
		),
	)
	with op.batch_alter_table("blocks", schema=None) as batch_op:
		batch_op.create_index(
			batch_op.f("ix_blocks_blocker_id"),
			["blocker_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_blocks_blocked_id"),
			["blocked_id"],
			unique=False,
		)


def downgrade() -> None:
	with op.batch_alter_table("blocks", schema=None) as batch_op:
		batch_op.drop_index(batch_op.f("ix_blocks_blocked_id"))
		batch_op.drop_index(batch_op.f("ix_blocks_blocker_id"))

	op.drop_table("blocks")

	with op.batch_alter_table("friendship_events", schema=None) as batch_op:
		batch_op.drop_index(batch_op.f("ix_friendship_events_friendship_id"))

	op.drop_table("friendship_events")

	with op.batch_alter_table("friendships", schema=None) as batch_op:
		batch_op.drop_index(batch_op.f("ix_friendships_addressee_id"))
		batch_op.drop_index(batch_op.f("ix_friendships_requester_id"))

	op.drop_table("friendships")
