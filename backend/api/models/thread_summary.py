"""thread summary model - stores condensed summaries of conversation segments."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.models.mixins import (
	MetadataJSONMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.message import Message
	from api.models.thread import Thread


class SummaryType(StrEnum):
	"""type of thread summary."""

	WINDOW = "window"
	CONDENSED = "condensed"


class ThreadSummary(
	TypeIDPrimaryKeyMixin,
	TimestampMixin,
	MetadataJSONMixin,
	Base,
):
	"""condensed summary of a conversation segment.

	window summaries cover a batch of messages (start_message_id to
	end_message_id). condensed summaries are produced by merging
	multiple window summaries together (summary-of-summaries).

	when a condensed summary replaces older summaries, those are
	marked via superseded_by pointing to the new condensed summary.
	"""

	__tablename__ = "thread_summaries"
	__typeid_prefix__ = "tsum"

	thread_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("threads.id", ondelete="CASCADE"),
		index=True,
	)
	type: Mapped[SummaryType] = mapped_column(
		StringEnum(SummaryType, length=20),
		default=SummaryType.WINDOW,
	)
	start_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
	)
	end_message_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="SET NULL"),
	)
	message_count: Mapped[int] = mapped_column(Integer, default=0)
	content: Mapped[str] = mapped_column(Text, default="")

	# self-referential FK for recursive condensation.
	# when this summary is superseded by a condensed summary,
	# superseded_by points to the replacement.
	superseded_by_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("thread_summaries.id", ondelete="SET NULL"),
	)

	# -- relationships --

	thread: Mapped[Thread] = relationship(
		"Thread",
		back_populates="summaries",
	)
	start_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys=[start_message_id],
	)
	end_message: Mapped[Message | None] = relationship(
		"Message",
		foreign_keys=[end_message_id],
	)
	superseded_by: Mapped[ThreadSummary | None] = relationship(
		"ThreadSummary",
		remote_side="ThreadSummary.id",
		foreign_keys=[superseded_by_id],
	)

	@property
	def is_superseded(self) -> bool:
		"""whether this summary has been replaced by a condensed summary."""
		return self.superseded_by_id is not None
