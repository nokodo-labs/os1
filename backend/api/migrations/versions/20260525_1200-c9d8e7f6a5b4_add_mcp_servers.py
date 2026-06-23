"""add MCP servers

Revision ID: c9d8e7f6a5b4
Revises: b8f3c1d2e4a5
Create Date: 2026-05-25 12:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "c9d8e7f6a5b4"
down_revision = "a7b8c9d2e4f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.create_table(
		"mcp_servers",
		sa.Column("name", sa.String(length=120), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("scope", sa.String(), nullable=False),
		sa.Column("owner_user_id", sa.String(length=90), nullable=True),
		sa.Column("transport", sa.String(), nullable=False),
		sa.Column("url", sa.String(length=2048), nullable=True),
		sa.Column("command", sa.String(length=1024), nullable=True),
		sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("env", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("auth_type", sa.String(), nullable=False),
		sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("encrypted_access_token", sa.String(length=4096), nullable=True),
		sa.Column("enabled", sa.Boolean(), nullable=False),
		sa.Column(
			"capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False
		),
		sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.Column("status", sa.String(), nullable=False),
		sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("last_error", sa.Text(), nullable=True),
		sa.Column(
			"discovered_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False
		),
		sa.Column(
			"discovered_resources",
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
		),
		sa.Column(
			"discovered_prompts",
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
		),
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
		sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_mcp_servers_enabled", "mcp_servers", ["enabled"])
	op.create_index("ix_mcp_servers_owner_user_id", "mcp_servers", ["owner_user_id"])
	op.create_index("ix_mcp_servers_scope", "mcp_servers", ["scope"])
	op.create_index(
		"uq_mcp_servers_global_name",
		"mcp_servers",
		["name"],
		unique=True,
		postgresql_where=sa.text("scope = 'global'"),
	)
	op.create_index(
		"uq_mcp_servers_user_name",
		"mcp_servers",
		["owner_user_id", "name"],
		unique=True,
		postgresql_where=sa.text("scope = 'user'"),
	)


def downgrade() -> None:
	op.drop_index("uq_mcp_servers_user_name", table_name="mcp_servers")
	op.drop_index("uq_mcp_servers_global_name", table_name="mcp_servers")
	op.drop_index("ix_mcp_servers_scope", table_name="mcp_servers")
	op.drop_index("ix_mcp_servers_owner_user_id", table_name="mcp_servers")
	op.drop_index("ix_mcp_servers_enabled", table_name="mcp_servers")
	op.drop_table("mcp_servers")
