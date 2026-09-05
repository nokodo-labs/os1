"""thread model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	DateTime,
	ForeignKey,
	Index,
	String,
	func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import thread_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	OriginMessageMixin,
	SoftDeleteMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.event import Event
	from api.models.message import Message
	from api.models.project import Project
	from api.models.task import Task
	from api.models.thread_participant import ThreadParticipant
	from api.models.thread_summary import ThreadSummary
	from api.models.user import User


class Thread(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	OriginMessageMixin,
	SoftDeleteMixin,
	Base,
):
	"""conversation container tying together messages, events, and tasks."""

	__tablename__ = "threads"
	__typeid_prefix__ = "thread"
	__table_args__ = (
		Index(
			"idx_threads_title_trgm",
			"title",
			postgresql_using="gin",
			postgresql_ops={"title": "gin_trgm_ops"},
		),
	)

	title: Mapped[str | None] = mapped_column(String(255), nullable=True)
	tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
	is_temporary: Mapped[bool] = mapped_column(default=False)
	last_activity_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	current_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey(
			"messages.id",
			ondelete="SET NULL",
			use_alter=True,
			name="fk_threads_current_message_id_messages",
		),
		index=True,
	)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="threads",
		innerjoin=True,
	)
	origin_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys="Thread.origin_message_id",
	)
	current_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys=[current_message_id],
		post_update=True,
	)
	participants: Mapped[list[ThreadParticipant]] = relationship(
		"ThreadParticipant",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	projects: Mapped[list[Project]] = relationship(
		"Project",
		secondary=thread_project_association,
		back_populates="threads",
	)
	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="thread",
		cascade="all, delete-orphan",
	)
	messages: Mapped[list[Message]] = relationship(
		"Message",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
		foreign_keys="Message.thread_id",
	)
	events: Mapped[list[Event]] = relationship(
		"Event",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
	tasks: Mapped[list[Task]] = relationship(
		"Task",
		back_populates="spawned_thread",
	)
	summaries: Mapped[list[ThreadSummary]] = relationship(
		"ThreadSummary",
		back_populates="thread",
		cascade="all, delete-orphan",
		passive_deletes=True,
	)
