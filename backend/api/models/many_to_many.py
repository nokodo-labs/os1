"""Association tables for model relationships."""

from sqlalchemy import Column, ForeignKey, String, Table

from api.core.database import Base
from api.models.common import TYPEID_LENGTH


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
