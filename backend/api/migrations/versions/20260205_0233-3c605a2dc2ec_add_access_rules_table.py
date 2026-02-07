"""add access_rules table

Revision ID: 3c605a2dc2ec
Revises: e6a981c1b388
Create Date: 2026-02-05 02:33:07.550014

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "3c605a2dc2ec"
down_revision = "e6a981c1b388"
branch_labels = None
depends_on = None


def upgrade() -> None:
	# --- access_rules table ---
	op.create_table(
		"access_rules",
		sa.Column("subject_user_id", sa.String(length=90), nullable=True),
		sa.Column("subject_group_id", sa.String(length=90), nullable=True),
		sa.Column("subject_role_id", sa.String(length=90), nullable=True),
		sa.Column("level", sa.String(length=20), nullable=False),
		sa.Column("order_index", sa.Integer(), nullable=False),
		sa.Column("thread_id", sa.String(length=90), nullable=True),
		sa.Column("project_id", sa.String(length=90), nullable=True),
		sa.Column("agent_id", sa.String(length=90), nullable=True),
		sa.Column("note_id", sa.String(length=90), nullable=True),
		sa.Column("memory_id", sa.String(length=90), nullable=True),
		sa.Column("task_id", sa.String(length=90), nullable=True),
		sa.Column("file_id", sa.String(length=90), nullable=True),
		sa.Column("plugin_id", sa.String(length=90), nullable=True),
		sa.Column("prompt_id", sa.String(length=90), nullable=True),
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
		sa.Column("metadata", sa.JSON(), nullable=False),
		sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["file_id"], ["files.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(
			["subject_group_id"], ["groups.id"], ondelete="CASCADE"
		),
		sa.ForeignKeyConstraint(["subject_role_id"], ["roles.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["plugin_id"], ["plugins.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint(
			"subject_user_id",
			"subject_group_id",
			"subject_role_id",
			"thread_id",
			"project_id",
			"agent_id",
			"note_id",
			"memory_id",
			"task_id",
			"file_id",
			"plugin_id",
			"prompt_id",
			name="uq_access_rule_subject_resource",
		),
		sa.CheckConstraint(
			"(CASE WHEN subject_user_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN subject_group_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN subject_role_id IS NULL THEN 0 ELSE 1 END) IN (0, 1)",
			name="ck_access_rules_single_principal",
		),
	)
	with op.batch_alter_table("access_rules", schema=None) as batch_op:
		batch_op.create_index(
			batch_op.f("ix_access_rules_agent_id"), ["agent_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_file_id"), ["file_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_memory_id"), ["memory_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_note_id"), ["note_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_plugin_id"), ["plugin_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_project_id"), ["project_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_prompt_id"), ["prompt_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_subject_group_id"),
			["subject_group_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_subject_role_id"),
			["subject_role_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_subject_user_id"),
			["subject_user_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_task_id"), ["task_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_rules_thread_id"), ["thread_id"], unique=False
		)

	# --- user_roles M2M table ---
	op.create_table(
		"user_roles",
		sa.Column(
			"user_id",
			sa.String(length=90),
			sa.ForeignKey("users.id", ondelete="CASCADE"),
			primary_key=True,
		),
		sa.Column(
			"role_id",
			sa.String(length=90),
			sa.ForeignKey("roles.id", ondelete="CASCADE"),
			primary_key=True,
		),
	)

	# --- roles table additions ---
	bind = op.get_bind()
	inspector = sa.inspect(bind)
	role_columns = {col["name"] for col in inspector.get_columns("roles")}
	with op.batch_alter_table("roles", schema=None) as batch_op:
		if "description" not in role_columns:
			batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
		if "default_permissions" not in role_columns:
			batch_op.add_column(
				sa.Column(
					"default_permissions",
					sa.JSON(),
					nullable=False,
					server_default="{}",
				)
			)
		if "permissions" in role_columns:
			batch_op.drop_column("permissions")

	# --- drop old ACL table ---
	with op.batch_alter_table("access_control_entries", schema=None) as batch_op:
		batch_op.drop_index(batch_op.f("ix_access_control_entries_agent_id"))
		batch_op.drop_index(batch_op.f("ix_access_control_entries_group_id"))
		batch_op.drop_index(batch_op.f("ix_access_control_entries_project_id"))
		batch_op.drop_index(batch_op.f("ix_access_control_entries_thread_id"))
		batch_op.drop_index(batch_op.f("ix_access_control_entries_user_id"))

	op.drop_table("access_control_entries")


def downgrade() -> None:
	# --- restore old ACL table ---
	op.create_table(
		"access_control_entries",
		sa.Column("id", sa.VARCHAR(length=90), autoincrement=False, nullable=False),
		sa.Column(
			"thread_id", sa.VARCHAR(length=90), autoincrement=False, nullable=True
		),
		sa.Column(
			"project_id", sa.VARCHAR(length=90), autoincrement=False, nullable=True
		),
		sa.Column("user_id", sa.VARCHAR(length=90), autoincrement=False, nullable=True),
		sa.Column(
			"group_id", sa.VARCHAR(length=90), autoincrement=False, nullable=True
		),
		sa.Column(
			"agent_id", sa.VARCHAR(length=90), autoincrement=False, nullable=True
		),
		sa.Column("role", sa.VARCHAR(), autoincrement=False, nullable=False),
		sa.Column(
			"created_at",
			postgresql.TIMESTAMP(timezone=True),
			server_default=sa.text("now()"),
			autoincrement=False,
			nullable=False,
		),
		sa.Column(
			"updated_at",
			postgresql.TIMESTAMP(timezone=True),
			server_default=sa.text("now()"),
			autoincrement=False,
			nullable=False,
		),
		sa.Column(
			"metadata",
			postgresql.JSON(astext_type=sa.Text()),
			autoincrement=False,
			nullable=False,
		),
		sa.ForeignKeyConstraint(
			["agent_id"],
			["agents.id"],
			name=op.f("access_control_entries_agent_id_fkey"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["group_id"],
			["groups.id"],
			name=op.f("access_control_entries_group_id_fkey"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["project_id"],
			["projects.id"],
			name=op.f("access_control_entries_project_id_fkey"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["thread_id"],
			["threads.id"],
			name=op.f("access_control_entries_thread_id_fkey"),
			ondelete="CASCADE",
		),
		sa.ForeignKeyConstraint(
			["user_id"],
			["users.id"],
			name=op.f("access_control_entries_user_id_fkey"),
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id", name=op.f("access_control_entries_pkey")),
	)
	with op.batch_alter_table("access_control_entries", schema=None) as batch_op:
		batch_op.create_index(
			batch_op.f("ix_access_control_entries_user_id"), ["user_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_control_entries_thread_id"),
			["thread_id"],
			unique=False,
		)
		batch_op.create_index(
			batch_op.f("ix_access_control_entries_project_id"),
			["project_id"],
			unique=False,
		)

	# --- restore roles table columns ---
	bind = op.get_bind()
	inspector = sa.inspect(bind)
	role_columns = {col["name"] for col in inspector.get_columns("roles")}
	with op.batch_alter_table("roles", schema=None) as batch_op:
		if "permissions" not in role_columns:
			batch_op.add_column(
				sa.Column(
					"permissions",
					sa.JSON(),
					nullable=False,
					server_default="{}",
				)
			)
		if "default_permissions" in role_columns:
			batch_op.drop_column("default_permissions")
		if "description" in role_columns:
			batch_op.drop_column("description")
		batch_op.create_index(
			batch_op.f("ix_access_control_entries_group_id"), ["group_id"], unique=False
		)
		batch_op.create_index(
			batch_op.f("ix_access_control_entries_agent_id"), ["agent_id"], unique=False
		)

	# --- remove roles table additions ---
	with op.batch_alter_table("roles", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column(
				"permissions",
				postgresql.JSON(astext_type=sa.Text()),
				autoincrement=False,
				nullable=False,
				server_default="[]",
			)
		)
		batch_op.drop_column("default_permissions")
		batch_op.drop_column("description")

	# --- drop user_roles M2M table ---
	op.drop_table("user_roles")

	# --- drop access_rules table ---
	with op.batch_alter_table("access_rules", schema=None) as batch_op:
		batch_op.drop_index(batch_op.f("ix_access_rules_thread_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_task_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_subject_user_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_subject_role_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_subject_group_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_prompt_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_project_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_plugin_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_note_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_memory_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_file_id"))
		batch_op.drop_index(batch_op.f("ix_access_rules_agent_id"))

	op.drop_table("access_rules")
