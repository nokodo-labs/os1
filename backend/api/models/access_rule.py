"""access rule model for unified resource sharing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from api.permissions import AccessLevel


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.file import File
	from api.models.group import Group
	from api.models.memory import Memory
	from api.models.note import Note
	from api.models.plugin import Plugin
	from api.models.project import Project
	from api.models.prompt import Prompt
	from api.models.role import Role
	from api.models.task import Task
	from api.models.thread import Thread
	from api.models.user import User


class AccessRule(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""
	unified access rule that grants a subject access to a resource.

	rules are evaluated in order (by order_index). the last matching rule wins.
	owner always has implicit admin access before any rules are evaluated.

	subjects:
	- user: grants access to a specific user
	- group: grants access to all members of a group
	- role: grants access to all users with a specific role (admin-only to create)
	- public: grants access to everyone (no principal fields set)

	access levels:
	- reader: can view the resource
	- editor: can view and modify the resource
	- admin: can view, modify, delete, and manage sharing for the resource
	"""

	__tablename__ = "access_rules"
	__typeid_prefix__ = "arule"

	# subject specification (exactly one, or none for public)
	subject_user_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	subject_group_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("groups.id", ondelete="CASCADE"),
		index=True,
	)
	subject_role_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("roles.id", ondelete="CASCADE"),
		index=True,
	)

	# access config
	level: Mapped[AccessLevel] = mapped_column(
		StringEnum(AccessLevel),
		default=AccessLevel.READER,
	)
	order_index: Mapped[int] = mapped_column(Integer, default=0)

	# resource FKs (exactly one must be set, or none for role defaults)
	thread_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	project_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("projects.id", ondelete="CASCADE"),
		index=True,
	)
	agent_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="CASCADE"),
		index=True,
	)
	note_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("notes.id", ondelete="CASCADE"),
		index=True,
	)
	memory_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("memories.id", ondelete="CASCADE"),
		index=True,
	)
	task_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("tasks.id", ondelete="CASCADE"),
		index=True,
	)
	file_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("files.id", ondelete="CASCADE"),
		index=True,
	)
	plugin_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("plugins.id", ondelete="CASCADE"),
		index=True,
	)
	prompt_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("prompts.id", ondelete="CASCADE"),
		index=True,
	)
	group_id: Mapped[str | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("groups.id", ondelete="CASCADE"),
		index=True,
	)

	thread: Mapped[Thread | None] = relationship(
		"Thread", back_populates="access_rules"
	)
	project: Mapped[Project | None] = relationship(
		"Project", back_populates="access_rules"
	)
	agent: Mapped[Agent | None] = relationship("Agent", back_populates="access_rules")
	note: Mapped[Note | None] = relationship("Note", back_populates="access_rules")
	memory: Mapped[Memory | None] = relationship(
		"Memory", back_populates="access_rules"
	)
	task: Mapped[Task | None] = relationship("Task", back_populates="access_rules")
	file: Mapped[File | None] = relationship("File", back_populates="access_rules")
	plugin: Mapped[Plugin | None] = relationship(
		"Plugin", back_populates="access_rules"
	)
	prompt: Mapped[Prompt | None] = relationship(
		"Prompt", back_populates="access_rules"
	)
	group: Mapped[Group | None] = relationship(
		"Group",
		foreign_keys="AccessRule.group_id",
		back_populates="resource_access_rules",
	)

	# subject relationships
	subject_user: Mapped[User | None] = relationship(
		"User",
		foreign_keys="AccessRule.subject_user_id",
	)
	subject_group: Mapped[Group | None] = relationship(
		"Group",
		foreign_keys="AccessRule.subject_group_id",
	)
	subject_role: Mapped[Role | None] = relationship(
		"Role",
		foreign_keys="AccessRule.subject_role_id",
	)

	__table_args__ = (
		# prevent duplicate rules for same subject on same resource
		UniqueConstraint(
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
			name="uq_access_rule_subject_resource",
		),
		CheckConstraint(
			"(CASE WHEN subject_user_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN subject_group_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN subject_role_id IS NULL THEN 0 ELSE 1 END) IN (0, 1)",
			name="ck_access_rules_single_principal",
		),
		# a group cannot grant itself access
		CheckConstraint(
			"subject_group_id IS NULL OR group_id IS NULL "
			"OR subject_group_id != group_id",
			name="ck_access_rules_no_self_group",
		),
	)
