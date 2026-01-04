"""Thread model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
	JSON,
	DateTime,
	ForeignKey,
	String,
	func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import thread_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	SoftDeleteMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.thread import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.acl import AccessControlEntry
	from api.models.event import Event
	from api.models.message import Message
	from api.models.project import Project
	from api.models.task import Task
	from api.models.thread_participant import ThreadParticipant
	from api.models.user import User


class Thread(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	SoftDeleteMixin,
	Base,
):
	"""Conversation container tying together messages, events, and tasks."""

	__tablename__ = "threads"
	__typeid_prefix__ = "thread"

	title: Mapped[str | None] = mapped_column(String(255), nullable=True)
	tags: Mapped[list[str]] = mapped_column(JSON, default=list)
	is_archived: Mapped[bool] = mapped_column(default=False)
	is_temporary: Mapped[bool] = mapped_column(default=False)
	last_activity_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		server_default=func.now(),
		onupdate=func.now(),
	)

	owner_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
	)
	spawned_from_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
		index=True,
	)
	current_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
		index=True,
	)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="threads",
		innerjoin=True,
	)
	spawned_from_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys=[spawned_from_message_id],
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
	access_control_entries: Mapped[list[AccessControlEntry]] = relationship(
		"AccessControlEntry",
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

	def to_sdk(self) -> SDKThread:
		"""convert thread to sdk thread using the current branch.

		the sdk thread only supports a linear message list.
		we derive the current root→leaf branch from current_message_id and the
		in-memory message list, avoiding lazy-loading relationships.
		"""
		if not self.current_message_id:
			sdk_messages: list[SDKMessage] = []
			return SDKThread(
				created_at=self.created_at,
				messages=sdk_messages,
				metadata=self.metadata_,
			)

		messages_by_id: dict[TypeID, Message] = {
			TypeID(msg.id): msg for msg in self.messages
		}
		branch: list[Message] = []
		cur_id: TypeID | None = self.current_message_id
		visited: set[TypeID] = set()
		while cur_id is not None:
			if cur_id in visited:
				break
			visited.add(cur_id)
			cur = messages_by_id.get(cur_id)
			if cur is None:
				break
			branch.insert(0, cur)
			cur_id = cur.parent_id

		sdk_messages = [msg.to_sdk() for msg in branch]
		return SDKThread(
			created_at=self.created_at,
			messages=sdk_messages,
			metadata=self.metadata_,
		)
