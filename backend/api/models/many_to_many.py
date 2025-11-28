"""Association tables for model relationships."""

from sqlalchemy import Column, ForeignKey, Table

from api.core.database import Base


thread_project_association = Table(
    "thread_projects",
    Base.metadata,
    Column(
        "thread_id",
        ForeignKey("threads.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
