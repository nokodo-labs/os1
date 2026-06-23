"""add calendar events and scheduled item recurrence support

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-05-01 12:00:00.000000

This migration makes reminder ownership explicit by creating one default
reminder list per user and moving null-list reminders into that list. That
container choice is not reversible without losing user intent, so downgrade
keeps the assigned list ids.

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from nokodo_ai.utils.typeid import new_typeid


# revision identifiers
revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

TYPEID_LENGTH = 90


def upgrade() -> None:
	_add_reminder_default_list_fields()
	_create_default_reminder_lists()
	_update_reminder_recurrence_shape()
	_create_calendar_tables()
	_add_calendar_access_rules()
	_create_calendar_event_tables()
	_add_event_resource_links()
	_add_notification_delivery_fields()


def downgrade() -> None:
	_drop_notification_delivery_fields()
	_drop_event_resource_links()
	_drop_calendar_event_tables()
	_drop_calendar_access_rules()
	_drop_calendar_tables()
	_restore_reminder_recurrence_shape()
	_drop_reminder_default_list_fields()


def _add_reminder_default_list_fields() -> None:
	with op.batch_alter_table("reminder_lists", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column(
				"is_default",
				sa.Boolean(),
				nullable=False,
				server_default=sa.false(),
			)
		)
		batch_op.create_index(
			"ix_reminder_lists_owner_default",
			["owner_id", "is_default"],
			unique=False,
		)
		batch_op.alter_column("is_default", server_default=None)


def _create_default_reminder_lists() -> None:
	connection = op.get_bind()
	owner_ids = [
		row[0]
		for row in connection.execute(sa.text("SELECT id FROM users ORDER BY id"))
	]
	default_owner_ids = {
		row[0]
		for row in connection.execute(
			sa.text("SELECT owner_id FROM reminder_lists WHERE is_default IS TRUE")
		)
	}
	rows = [
		{
			"id": str(new_typeid("reml")),
			"owner_id": owner_id,
			"name": "reminders",
			"description": None,
			"color": "#22c55e",
			"icon": None,
			"position": 0.0,
			"metadata": {},
			"is_default": True,
		}
		for owner_id in owner_ids
		if owner_id not in default_owner_ids
	]
	if rows:
		op.bulk_insert(
			sa.table(
				"reminder_lists",
				sa.column("id", sa.String(TYPEID_LENGTH)),
				sa.column("owner_id", sa.String(TYPEID_LENGTH)),
				sa.column("name", sa.String(100)),
				sa.column("description", sa.String(500)),
				sa.column("color", sa.String(7)),
				sa.column("icon", sa.String(50)),
				sa.column("position", sa.Float()),
				sa.column("metadata", postgresql.JSONB()),
				sa.column("is_default", sa.Boolean()),
			),
			rows,
		)

	op.execute(
		"""
		UPDATE reminders AS reminder
		SET list_id = default_list.id
		FROM reminder_lists AS default_list
		WHERE reminder.list_id IS NULL
			AND default_list.owner_id = reminder.owner_id
			AND default_list.is_default IS TRUE
		"""
	)


def _update_reminder_recurrence_shape() -> None:
	with op.batch_alter_table("reminders", schema=None) as batch_op:
		batch_op.drop_constraint("reminders_list_id_fkey", type_="foreignkey")
		batch_op.drop_constraint("reminders_parent_id_fkey", type_="foreignkey")
		batch_op.alter_column(
			"list_id",
			existing_type=sa.String(TYPEID_LENGTH),
			nullable=False,
		)
		batch_op.alter_column(
			"recurrence",
			existing_type=sa.String(255),
			type_=postgresql.JSONB(astext_type=sa.Text()),
			existing_nullable=True,
			postgresql_using=_recurrence_string_to_jsonb_sql("recurrence"),
		)
		batch_op.add_column(
			sa.Column("recurrence_until", sa.DateTime(timezone=True), nullable=True)
		)
		batch_op.add_column(
			sa.Column("series_origin_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.create_foreign_key(
			"reminders_list_id_fkey",
			"reminder_lists",
			["list_id"],
			["id"],
			ondelete="CASCADE",
		)
		batch_op.create_foreign_key(
			"reminders_series_origin_id_fkey",
			"reminders",
			["series_origin_id"],
			["id"],
		)
		batch_op.create_foreign_key(
			"reminders_parent_id_fkey",
			"reminders",
			["parent_id"],
			["id"],
			ondelete="CASCADE",
		)
		batch_op.create_index(
			"ix_reminders_recurrence_until",
			["recurrence_until"],
			unique=False,
		)

	op.create_table(
		"reminder_overrides",
		sa.Column("reminder_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column(
			"original_occurrence_at",
			sa.DateTime(timezone=True),
			nullable=False,
		),
		sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
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
			["reminder_id"],
			["reminders.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("reminder_id", "original_occurrence_at"),
	)
	op.create_index(
		"ix_reminder_overrides_reminder_original",
		"reminder_overrides",
		["reminder_id", "original_occurrence_at"],
		unique=False,
	)


def _create_calendar_tables() -> None:
	op.create_table(
		"calendars",
		sa.Column("owner_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("name", sa.String(100), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("color", sa.String(7), nullable=False),
		sa.Column("position", sa.Float(), nullable=False),
		sa.Column("is_default", sa.Boolean(), nullable=False),
		sa.Column("timezone", sa.String(64), nullable=True),
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
		sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("id"),
		sa.UniqueConstraint("id", "owner_id", name="uq_calendars_id_owner"),
		sa.UniqueConstraint("owner_id", "name", name="uq_calendars_owner_name"),
	)
	with op.batch_alter_table("calendars", schema=None) as batch_op:
		batch_op.create_index("ix_calendars_owner_id", ["owner_id"], unique=False)
		batch_op.create_index(
			"ix_calendars_owner_default",
			["owner_id", "is_default"],
			unique=False,
		)
		batch_op.create_index(
			"idx_calendars_name_trgm",
			["name"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"name": "gin_trgm_ops"},
		)

	op.create_table(
		"calendar_projects",
		sa.Column("calendar_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("project_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.ForeignKeyConstraint(["calendar_id"], ["calendars.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
		sa.PrimaryKeyConstraint("calendar_id", "project_id"),
	)


def _add_calendar_access_rules() -> None:
	with op.batch_alter_table("access_rules", schema=None) as batch_op:
		batch_op.drop_constraint("uq_access_rule_subject_resource", type_="unique")
		batch_op.add_column(
			sa.Column("calendar_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.create_index(
			"ix_access_rules_calendar_id",
			["calendar_id"],
			unique=False,
		)
		batch_op.create_foreign_key(
			"fk_access_rules_calendar_id_calendars",
			"calendars",
			["calendar_id"],
			["id"],
			ondelete="CASCADE",
		)
		batch_op.create_unique_constraint(
			"uq_access_rule_subject_resource",
			[
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
				"group_id",
				"reminder_list_id",
				"calendar_id",
			],
		)


def _create_calendar_event_tables() -> None:
	op.create_table(
		"calendar_events",
		sa.Column("owner_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("title", sa.String(200), nullable=False),
		sa.Column("description", sa.Text(), nullable=True),
		sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
		sa.Column("all_day", sa.Boolean(), nullable=False),
		sa.Column("calendar_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column("timezone", sa.String(64), nullable=True),
		sa.Column("recurrence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column("recurrence_until", sa.DateTime(timezone=True), nullable=True),
		sa.Column("series_origin_id", sa.String(TYPEID_LENGTH), nullable=True),
		sa.Column("notification_offsets", sa.ARRAY(sa.Integer()), nullable=False),
		sa.Column("location", sa.String(255), nullable=True),
		sa.Column("virtual_url", sa.String(512), nullable=True),
		sa.Column("labels", sa.ARRAY(sa.String(50)), nullable=False),
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
		sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
		sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["series_origin_id"], ["calendar_events.id"]),
		sa.ForeignKeyConstraint(
			["calendar_id", "owner_id"],
			["calendars.id", "calendars.owner_id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("id"),
	)
	with op.batch_alter_table("calendar_events", schema=None) as batch_op:
		batch_op.create_index("ix_calendar_events_owner_id", ["owner_id"], unique=False)
		batch_op.create_index("ix_calendar_events_start_at", ["start_at"], unique=False)
		batch_op.create_index("ix_calendar_events_end_at", ["end_at"], unique=False)
		batch_op.create_index(
			"ix_calendar_events_recurrence_until",
			["recurrence_until"],
			unique=False,
		)
		batch_op.create_index(
			"ix_calendar_events_owner_start",
			["owner_id", "start_at"],
			unique=False,
		)
		batch_op.create_index(
			"ix_calendar_events_owner_end",
			["owner_id", "end_at"],
			unique=False,
		)
		batch_op.create_index(
			"ix_calendar_events_owner_calendar",
			["owner_id", "calendar_id"],
			unique=False,
		)
		batch_op.create_index(
			"ix_calendar_events_calendar_start",
			["calendar_id", "start_at"],
			unique=False,
		)
		batch_op.create_index(
			"ix_calendar_events_calendar_recurrence_until",
			["calendar_id", "recurrence_until"],
			unique=False,
		)
		batch_op.create_index(
			"idx_calendar_events_title_trgm",
			["title"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"title": "gin_trgm_ops"},
		)
		batch_op.create_index(
			"idx_calendar_events_description_trgm",
			["description"],
			unique=False,
			postgresql_using="gin",
			postgresql_ops={"description": "gin_trgm_ops"},
		)

	op.create_table(
		"calendar_event_overrides",
		sa.Column("event_id", sa.String(TYPEID_LENGTH), nullable=False),
		sa.Column(
			"original_occurrence_at",
			sa.DateTime(timezone=True),
			nullable=False,
		),
		sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("new_start_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("new_end_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column(
			"payload_patch",
			postgresql.JSONB(astext_type=sa.Text()),
			nullable=False,
		),
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
			["event_id"],
			["calendar_events.id"],
			ondelete="CASCADE",
		),
		sa.PrimaryKeyConstraint("event_id", "original_occurrence_at"),
	)
	op.create_index(
		"ix_calendar_event_overrides_event_original",
		"calendar_event_overrides",
		["event_id", "original_occurrence_at"],
		unique=False,
	)


def _add_event_resource_links() -> None:
	with op.batch_alter_table("events", schema=None) as batch_op:
		batch_op.add_column(
			sa.Column("calendar_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.add_column(
			sa.Column("calendar_event_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.add_column(
			sa.Column("reminder_list_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.add_column(
			sa.Column("reminder_id", sa.String(TYPEID_LENGTH), nullable=True)
		)
		batch_op.create_index("ix_events_calendar_id", ["calendar_id"], unique=False)
		batch_op.create_index(
			"ix_events_calendar_event_id",
			["calendar_event_id"],
			unique=False,
		)
		batch_op.create_index(
			"ix_events_reminder_list_id",
			["reminder_list_id"],
			unique=False,
		)
		batch_op.create_index("ix_events_reminder_id", ["reminder_id"], unique=False)
		batch_op.create_foreign_key(
			"fk_events_calendar_id_calendars",
			"calendars",
			["calendar_id"],
			["id"],
			ondelete="SET NULL",
		)
		batch_op.create_foreign_key(
			"fk_events_calendar_event_id_calendar_events",
			"calendar_events",
			["calendar_event_id"],
			["id"],
			ondelete="SET NULL",
		)
		batch_op.create_foreign_key(
			"fk_events_reminder_list_id_reminder_lists",
			"reminder_lists",
			["reminder_list_id"],
			["id"],
			ondelete="SET NULL",
		)
		batch_op.create_foreign_key(
			"fk_events_reminder_id_reminders",
			"reminders",
			["reminder_id"],
			["id"],
			ondelete="SET NULL",
		)


def _add_notification_delivery_fields() -> None:
	with op.batch_alter_table("notifications", schema=None) as batch_op:
		batch_op.add_column(sa.Column("delivery_key", sa.String(512), nullable=True))
		batch_op.add_column(
			sa.Column("notify_at", sa.DateTime(timezone=True), nullable=True)
		)
		batch_op.create_unique_constraint(
			"uq_notifications_delivery_key",
			["delivery_key"],
		)
		batch_op.create_index("ix_notifications_notify_at", ["notify_at"], unique=False)


def _drop_notification_delivery_fields() -> None:
	with op.batch_alter_table("notifications", schema=None) as batch_op:
		batch_op.drop_index("ix_notifications_notify_at")
		batch_op.drop_constraint("uq_notifications_delivery_key", type_="unique")
		batch_op.drop_column("notify_at")
		batch_op.drop_column("delivery_key")


def _restore_reminder_recurrence_shape() -> None:
	op.drop_index(
		"ix_reminder_overrides_reminder_original",
		table_name="reminder_overrides",
	)
	op.drop_table("reminder_overrides")

	with op.batch_alter_table("reminders", schema=None) as batch_op:
		batch_op.drop_index("ix_reminders_recurrence_until")
		batch_op.drop_constraint("reminders_series_origin_id_fkey", type_="foreignkey")
		batch_op.drop_constraint("reminders_list_id_fkey", type_="foreignkey")
		batch_op.drop_constraint("reminders_parent_id_fkey", type_="foreignkey")
		batch_op.alter_column(
			"list_id",
			existing_type=sa.String(TYPEID_LENGTH),
			nullable=True,
		)
		batch_op.alter_column(
			"recurrence",
			existing_type=postgresql.JSONB(astext_type=sa.Text()),
			type_=sa.String(255),
			existing_nullable=True,
			postgresql_using="recurrence->'rrule'->>0",
		)
		batch_op.create_foreign_key(
			"reminders_list_id_fkey",
			"reminder_lists",
			["list_id"],
			["id"],
		)
		batch_op.create_foreign_key(
			"reminders_parent_id_fkey",
			"reminders",
			["parent_id"],
			["id"],
		)
		batch_op.drop_column("series_origin_id")
		batch_op.drop_column("recurrence_until")


def _drop_reminder_default_list_fields() -> None:
	with op.batch_alter_table("reminder_lists", schema=None) as batch_op:
		batch_op.drop_index("ix_reminder_lists_owner_default")
		batch_op.drop_column("is_default")


def _drop_calendar_event_tables() -> None:
	op.drop_index(
		"ix_calendar_event_overrides_event_original",
		table_name="calendar_event_overrides",
	)
	op.drop_table("calendar_event_overrides")

	with op.batch_alter_table("calendar_events", schema=None) as batch_op:
		batch_op.drop_index(
			"idx_calendar_events_description_trgm",
			postgresql_using="gin",
		)
		batch_op.drop_index("idx_calendar_events_title_trgm", postgresql_using="gin")
		batch_op.drop_index("ix_calendar_events_calendar_recurrence_until")
		batch_op.drop_index("ix_calendar_events_calendar_start")
		batch_op.drop_index("ix_calendar_events_owner_calendar")
		batch_op.drop_index("ix_calendar_events_owner_end")
		batch_op.drop_index("ix_calendar_events_owner_start")
		batch_op.drop_index("ix_calendar_events_recurrence_until")
		batch_op.drop_index("ix_calendar_events_end_at")
		batch_op.drop_index("ix_calendar_events_start_at")
		batch_op.drop_index("ix_calendar_events_owner_id")

	op.drop_table("calendar_events")


def _drop_event_resource_links() -> None:
	with op.batch_alter_table("events", schema=None) as batch_op:
		batch_op.drop_constraint(
			"fk_events_reminder_id_reminders",
			type_="foreignkey",
		)
		batch_op.drop_constraint(
			"fk_events_reminder_list_id_reminder_lists",
			type_="foreignkey",
		)
		batch_op.drop_constraint(
			"fk_events_calendar_event_id_calendar_events",
			type_="foreignkey",
		)
		batch_op.drop_constraint(
			"fk_events_calendar_id_calendars",
			type_="foreignkey",
		)
		batch_op.drop_index("ix_events_reminder_id")
		batch_op.drop_index("ix_events_reminder_list_id")
		batch_op.drop_index("ix_events_calendar_event_id")
		batch_op.drop_index("ix_events_calendar_id")
		batch_op.drop_column("reminder_id")
		batch_op.drop_column("reminder_list_id")
		batch_op.drop_column("calendar_event_id")
		batch_op.drop_column("calendar_id")


def _drop_calendar_access_rules() -> None:
	with op.batch_alter_table("access_rules", schema=None) as batch_op:
		batch_op.drop_constraint("uq_access_rule_subject_resource", type_="unique")
		batch_op.drop_constraint(
			"fk_access_rules_calendar_id_calendars",
			type_="foreignkey",
		)
		batch_op.drop_index("ix_access_rules_calendar_id")
		batch_op.drop_column("calendar_id")
		batch_op.create_unique_constraint(
			"uq_access_rule_subject_resource",
			[
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
				"group_id",
				"reminder_list_id",
			],
		)


def _drop_calendar_tables() -> None:
	op.drop_table("calendar_projects")
	with op.batch_alter_table("calendars", schema=None) as batch_op:
		batch_op.drop_index("idx_calendars_name_trgm", postgresql_using="gin")
		batch_op.drop_index("ix_calendars_owner_default")
		batch_op.drop_index("ix_calendars_owner_id")

	op.drop_table("calendars")


def _recurrence_string_to_jsonb_sql(column_name: str) -> str:
	return (
		f"CASE WHEN {column_name} IS NULL OR btrim({column_name}) = '' "
		f"THEN NULL ELSE jsonb_build_object("
		f"'rrule', ARRAY[{column_name}], "
		f"'rdate', ARRAY[]::text[], "
		f"'exdate', ARRAY[]::text[], "
		f"'timezone', NULL) END"
	)
