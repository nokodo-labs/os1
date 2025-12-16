"""initial migration.

Revision ID: c76fff12fadc
Revises:
Create Date: 2025-12-08 21:02:24.734545

"""

import sqlalchemy as sa
from alembic import op


revision = "c76fff12fadc"
down_revision = None
branch_labels = None
depends_on = None


TYPEID_LENGTH = 90


def upgrade() -> None:
	op.create_table(
		"roles",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=50), nullable=False),
		sa.Column("permissions", sa.JSON(), nullable=False),
		sa.Column("quotas", sa.JSON(), nullable=False),
		sa.Column("priority", sa.Integer(), nullable=False),
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_roles_name", "roles", ["name"], unique=True)

	op.create_table(
		"users",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("email", sa.String(length=255), nullable=False),
		sa.Column("display_name", sa.String(length=150), nullable=True),
		sa.Column("avatar_url", sa.String(length=512), nullable=True),
		sa.Column("hashed_password", sa.String(length=255), nullable=False),
		sa.Column("is_active", sa.Boolean(), nullable=False),
		sa.Column("is_superuser", sa.Boolean(), nullable=False),
		sa.Column("preferences", sa.JSON(), nullable=False),
		sa.Column("integration_tokens", sa.JSON(), nullable=False),
		sa.Column("usage_quotas", sa.JSON(), nullable=False),
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
		sa.Column("role_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_users_id", "users", ["id"], unique=False)
	op.create_index("ix_users_email", "users", ["email"], unique=True)

	op.create_table(
		"providers",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("adapter_type", sa.String(length=100), nullable=False),
		sa.Column("provider_type", sa.String(), nullable=False),
		sa.Column("base_url", sa.String(length=255), nullable=True),
		sa.Column("encrypted_api_key", sa.String(length=1024), nullable=True),
		sa.Column("model_prefix", sa.String(length=50), nullable=True),
		sa.Column("additional_headers", sa.JSON(), nullable=True),
		sa.Column("status", sa.String(), nullable=False),
		sa.Column("is_autofetch_enabled", sa.Boolean(), nullable=False),
		sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("name"),
	)

	op.create_table(
		"models",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("provider_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=150), nullable=False),
		sa.Column("display_name", sa.String(length=150), nullable=True),
		sa.Column("model_type", sa.String(), nullable=False),
		sa.Column("endpoint", sa.String(length=255), nullable=True),
		sa.Column("capabilities", sa.JSON(), nullable=False),
		sa.Column("context_window", sa.Integer(), nullable=True),
		sa.Column("input_cost", sa.Float(), nullable=True),
		sa.Column("output_cost", sa.Float(), nullable=True),
		sa.Column("enabled", sa.Boolean(), nullable=False),
		sa.Column("is_autofetched", sa.Boolean(), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(
			["provider_id"],
			["providers.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_models_provider_id", "models", ["provider_id"], unique=False)

	op.create_table(
		"agents",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("system_prompt", sa.Text(), nullable=True),
		sa.Column("visibility", sa.String(), nullable=False),
		sa.Column("tool_ids", sa.JSON(), nullable=False),
		sa.Column("config", sa.JSON(), nullable=False),
		sa.Column("model_id", sa.String(length=TYPEID_LENGTH), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(
			["model_id"],
			["models.id"],
			ondelete="SET NULL",
		),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("name"),
	)

	op.create_table(
		"threads",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("title", sa.String(length=255), nullable=True),
		sa.Column("tags", sa.JSON(), nullable=False),
		sa.Column("is_archived", sa.Boolean(), nullable=False),
		sa.Column(
			"last_activity_at",
			sa.DateTime(timezone=True),
			server_default=sa.text("now()"),
			nullable=False,
		),
		sa.Column("owner_id", sa.String(length=TYPEID_LENGTH), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)

	op.create_table(
		"projects",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("description", sa.String(length=500), nullable=True),
		sa.Column("owner_id", sa.String(length=TYPEID_LENGTH), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)

	op.create_table(
		"thread_projects",
		sa.Column("thread_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("project_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("thread_id", "project_id"),
	)

	op.create_table(
		"groups",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(length=100), nullable=False),
		sa.Column("description", sa.String(length=500), nullable=True),
		sa.Column("owner_id", sa.String(length=TYPEID_LENGTH), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)

	op.create_table(
		"group_memberships",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("group_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("role", sa.String(), nullable=False),
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
	)

	op.create_table(
		"tasks",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("task_type", sa.String(), nullable=False),
		sa.Column("status", sa.String(), nullable=False),
		sa.Column("progress", sa.Integer(), nullable=True),
		sa.Column("stage", sa.String(length=100), nullable=True),
		sa.Column("result", sa.JSON(), nullable=True),
		sa.Column("spawned_thread_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(
			["spawned_thread_id"], ["threads.id"], ondelete="SET NULL"
		),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_tasks_user_id", "tasks", ["user_id"], unique=False)

	op.create_table(
		"messages",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("thread_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("task_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("sender_agent_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("sender_user_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("type", sa.String(), nullable=False),
		sa.Column("content", sa.Text(), nullable=False),
		sa.Column("attachments", sa.JSON(), nullable=False),
		sa.Column("tool_calls", sa.JSON(), nullable=False),
		sa.Column("token_usage", sa.JSON(), nullable=True),
		sa.Column("read_by", sa.JSON(), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(
			["sender_agent_id"],
			["agents.id"],
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["sender_user_id"],
			["users.id"],
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["task_id"],
			["tasks.id"],
			ondelete="SET NULL",
		),
		sa.ForeignKeyConstraint(
			["thread_id"],
			["threads.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index(
		"ix_messages_sender_agent_id", "messages", ["sender_agent_id"], unique=False
	)
	op.create_index(
		"ix_messages_sender_user_id", "messages", ["sender_user_id"], unique=False
	)
	op.create_index("ix_messages_task_id", "messages", ["task_id"], unique=False)
	op.create_index("ix_messages_thread_id", "messages", ["thread_id"], unique=False)

	op.create_table(
		"access_control_entries",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("thread_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("project_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("group_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("agent_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("role", sa.String(), nullable=False),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index(
		"ix_access_control_entries_agent_id",
		"access_control_entries",
		["agent_id"],
		unique=False,
	)
	op.create_index(
		"ix_access_control_entries_group_id",
		"access_control_entries",
		["group_id"],
		unique=False,
	)
	op.create_index(
		"ix_access_control_entries_project_id",
		"access_control_entries",
		["project_id"],
		unique=False,
	)
	op.create_index(
		"ix_access_control_entries_thread_id",
		"access_control_entries",
		["thread_id"],
		unique=False,
	)
	op.create_index(
		"ix_access_control_entries_user_id",
		"access_control_entries",
		["user_id"],
		unique=False,
	)

	op.create_table(
		"memories",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("content", sa.Text(), nullable=False),
		sa.Column("source_message_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("embedding", sa.LargeBinary(), nullable=True),
		sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("confidence", sa.Float(), nullable=True),
		sa.Column("category", sa.String(length=50), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(
			["source_message_id"], ["messages.id"], ondelete="SET NULL"
		),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_memories_user_id", "memories", ["user_id"], unique=False)

	op.create_table(
		"events",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("scope", sa.String(), nullable=False),
		sa.Column("scope_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("type", sa.String(length=100), nullable=False),
		sa.Column("data", sa.JSON(), nullable=False),
		sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("version", sa.Integer(), nullable=False),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("thread_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("message_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("task_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("project_id", sa.String(length=TYPEID_LENGTH), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
		sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
		sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index("ix_events_thread_id", "events", ["thread_id"], unique=False)
	op.create_index("ix_events_user_id", "events", ["user_id"], unique=False)

	op.create_table(
		"notifications",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("user_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("event_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("dismissed", sa.Boolean(), nullable=False),
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
		sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
		sa.PrimaryKeyConstraint("id"),
	)
	op.create_index(
		"ix_notifications_event_id", "notifications", ["event_id"], unique=False
	)
	op.create_index(
		"ix_notifications_user_id", "notifications", ["user_id"], unique=False
	)

	op.create_table(
		"reminders",
		sa.Column("id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("owner_id", sa.String(length=TYPEID_LENGTH), nullable=False),
		sa.Column("content", sa.String(length=500), nullable=False),
		sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("recurrence", sa.String(length=50), nullable=True),
		sa.Column("status", sa.String(), nullable=False),
		sa.Column("notification_channels", sa.JSON(), nullable=False),
		sa.Column("source_thread_id", sa.String(length=TYPEID_LENGTH), nullable=True),
		sa.Column("external_sync", sa.JSON(), nullable=True),
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
		sa.ForeignKeyConstraint(["source_thread_id"], ["threads.id"]),
		sa.PrimaryKeyConstraint("id"),
	)


def downgrade() -> None:
	op.drop_table("reminders")
	op.drop_index("ix_notifications_user_id", table_name="notifications")
	op.drop_index("ix_notifications_event_id", table_name="notifications")
	op.drop_table("notifications")
	op.drop_index("ix_events_user_id", table_name="events")
	op.drop_index("ix_events_thread_id", table_name="events")
	op.drop_table("events")
	op.drop_index("ix_memories_user_id", table_name="memories")
	op.drop_table("memories")
	op.drop_index(
		"ix_access_control_entries_user_id", table_name="access_control_entries"
	)
	op.drop_index(
		"ix_access_control_entries_thread_id", table_name="access_control_entries"
	)
	op.drop_index(
		"ix_access_control_entries_project_id", table_name="access_control_entries"
	)
	op.drop_index(
		"ix_access_control_entries_group_id", table_name="access_control_entries"
	)
	op.drop_index(
		"ix_access_control_entries_agent_id", table_name="access_control_entries"
	)
	op.drop_table("access_control_entries")
	op.drop_index("ix_messages_thread_id", table_name="messages")
	op.drop_index("ix_messages_task_id", table_name="messages")
	op.drop_index("ix_messages_sender_user_id", table_name="messages")
	op.drop_index("ix_messages_sender_agent_id", table_name="messages")
	op.drop_table("messages")
	op.drop_index("ix_tasks_user_id", table_name="tasks")
	op.drop_table("tasks")
	op.drop_table("group_memberships")
	op.drop_table("groups")
	op.drop_table("thread_projects")
	op.drop_table("projects")
	op.drop_table("threads")
	op.drop_table("agents")
	op.drop_index("ix_models_provider_id", table_name="models")
	op.drop_table("models")
	op.drop_table("providers")
	op.drop_index("ix_users_email", table_name="users")
	op.drop_index("ix_users_id", table_name="users")
	op.drop_index("ix_users_username", table_name="users")
	op.drop_table("users")
	op.drop_index("ix_roles_name", table_name="roles")
	op.drop_table("roles")
