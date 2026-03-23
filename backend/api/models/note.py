"""Note model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import TYPEID_LENGTH, Base
from api.models.many_to_many import note_project_association
from api.models.mixins import (
	MetadataJSONMixin,
	SoftDeleteMixin,
	TimestampMixin,
	TypeIDPrimaryKeyMixin,
)
from nokodo_ai.utils.typeid import TypeID


if TYPE_CHECKING:
	from api.models.access_rule import AccessRule
	from api.models.project import Project
	from api.models.user import User


class Note(
	TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, SoftDeleteMixin, Base
):
	"""Simple markdown notes with labels."""

	__tablename__ = "notes"
	__typeid_prefix__ = "note"
	__table_args__ = (
		Index(
			"idx_notes_title_trgm",
			"title",
			postgresql_using="gin",
			postgresql_ops={"title": "gin_trgm_ops"},
		),
		Index(
			"idx_notes_content_trgm",
			"content",
			postgresql_using="gin",
			postgresql_ops={"content": "gin_trgm_ops"},
		),
	)

	user_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		ForeignKey("users.id"),
		index=True,
	)
	title: Mapped[str] = mapped_column(String(255))
	content: Mapped[str] = mapped_column(Text(), default="")
	labels: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)

	owner: Mapped[User] = relationship(
		"User",
		back_populates="notes",
		lazy="selectin",
	)
	projects: Mapped[list[Project]] = relationship(
		"Project",
		secondary=note_project_association,
		back_populates="notes",
	)

	@property
	def project_ids(self) -> list[TypeID]:
		"""IDs of linked projects (requires projects to be loaded)."""
		return [p.id for p in self.projects]

	access_rules: Mapped[list[AccessRule]] = relationship(
		"AccessRule",
		back_populates="note",
		cascade="all, delete-orphan",
	)
