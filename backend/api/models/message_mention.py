"""message mention model."""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from api.permissions import MentionableSubjectType
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.agent import Agent
	from api.models.group import Group
	from api.models.message import Message
	from api.models.user import User


def subject_fk_name(subject_type: MentionableSubjectType) -> str:
	"""column holding the mentioned subject id for this subject type."""
	return f"{subject_type.value}_id"


class MessageMention(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""a subject a message addresses.

	addressing only: what a mention DOES depends on the kind. an agent may be
	invoked by one (see ``invoke_on_mention``); a user or group is addressed for
	the humans reading, and carries no delivery behavior yet.
	"""

	__tablename__ = "message_mentions"
	__typeid_prefix__ = "ment"
	__table_args__ = (
		CheckConstraint(
			"(CASE WHEN agent_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN user_id IS NULL THEN 0 ELSE 1 END + "
			"CASE WHEN group_id IS NULL THEN 0 ELSE 1 END) = 1",
			name="ck_message_mentions_single_subject",
		),
		Index(
			"uq_message_mentions_message_agent",
			"message_id",
			"agent_id",
			unique=True,
			postgresql_where=text("agent_id IS NOT NULL"),
		),
		Index(
			"uq_message_mentions_message_user",
			"message_id",
			"user_id",
			unique=True,
			postgresql_where=text("user_id IS NOT NULL"),
		),
		Index(
			"uq_message_mentions_message_group",
			"message_id",
			"group_id",
			unique=True,
			postgresql_where=text("group_id IS NOT NULL"),
		),
	)

	message_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	position: Mapped[int] = mapped_column()
	agent_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("agents.id", ondelete="CASCADE"),
		index=True,
	)
	user_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id", ondelete="CASCADE"),
		index=True,
	)
	group_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("groups.id", ondelete="CASCADE"),
		index=True,
	)

	message: Mapped[Message] = relationship(
		"Message",
		back_populates="mention_links",
		foreign_keys=[message_id],
	)
	agent: Mapped[Agent | None] = relationship("Agent", foreign_keys=[agent_id])
	user: Mapped[User | None] = relationship("User", foreign_keys=[user_id])
	group: Mapped[Group | None] = relationship("Group", foreign_keys=[group_id])

	@property
	def subject_ref(self) -> dict[str, object]:
		"""public subject reference for this mention."""
		for subject_type in MentionableSubjectType:
			value = self.__dict__.get(subject_fk_name(subject_type))
			if value is not None:
				return {"type": subject_type, "id": value}
		raise RuntimeError("message mention has no subject")
