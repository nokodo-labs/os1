"""association tables for model relationships."""

from sqlalchemy import Column, ForeignKey, String, Table

from api.models.base import TYPEID_LENGTH, Base


thread_project_association = Table(
	"thread_projects",
	Base.metadata,
	Column(
		"thread_id",
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"project_id",
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

file_project_association = Table(
	"file_projects",
	Base.metadata,
	Column(
		"file_id",
		String(TYPEID_LENGTH),
		ForeignKey("files.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"project_id",
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

note_project_association = Table(
	"note_projects",
	Base.metadata,
	Column(
		"note_id",
		String(TYPEID_LENGTH),
		ForeignKey("notes.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"project_id",
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

reminder_list_project_association = Table(
	"reminder_list_projects",
	Base.metadata,
	Column(
		"reminder_list_id",
		String(TYPEID_LENGTH),
		ForeignKey("reminder_lists.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"project_id",
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		primary_key=True,
	),
)

user_role_association = Table(
	"user_roles",
	Base.metadata,
	Column(
		"user_id",
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		primary_key=True,
	),
	Column(
		"role_id",
		String(TYPEID_LENGTH),
		ForeignKey("roles.id", ondelete="CASCADE"),
		primary_key=True,
	),
)
