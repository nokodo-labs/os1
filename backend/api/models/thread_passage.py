"""persisted transcript passage and enrichment data."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import TYPEID_LENGTH, Base
from api.models.mixins import TimestampMixin, TypeIDPrimaryKeyMixin
from nokodo_ai.utils.typeid import TypeID


class ThreadPassage(TypeIDPrimaryKeyMixin, TimestampMixin, Base):
	"""persisted transcript passage used to rebuild thread content vectors.

	the owning thread is reached through the first message of the span; see
	``api.v1.service.threads.passages`` for the canonical traversal.
	"""

	__tablename__ = "thread_passages"
	__typeid_prefix__ = "psg"
	__table_args__ = (
		UniqueConstraint(
			"first_message_id",
			"last_message_id",
			"part_index",
			name="uq_thread_passages_span",
		),
	)

	first_message_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	"""first message included in the persisted passage span."""
	last_message_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	"""last message included in the persisted passage span."""
	part_index: Mapped[int] = mapped_column(Integer, default=0)
	"""zero-based slice index when one oversized message produces multiple passages."""
	content_hash: Mapped[str] = mapped_column(String(64))
	"""SHA-256 digest used to detect changes within a stable passage span."""
	anchor_message_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("messages.id", ondelete="CASCADE"),
		index=True,
	)
	"""first non-overlap message used for branch filtering and result navigation."""
	content: Mapped[str] = mapped_column(Text)
	enrichment: Mapped[str | None] = mapped_column(Text)
	enrichment_model_id: Mapped[TypeID | None] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("models.id", ondelete="SET NULL"),
	)
	"""model used to generate the passage enrichment."""
	enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
	enrichment_pipeline_v: Mapped[int | None] = mapped_column(Integer)
	"""passage enrichment pipeline version used for the stored enrichment."""
