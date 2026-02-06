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
