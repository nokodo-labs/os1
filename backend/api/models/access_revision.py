"""revision state for one resource's resolved access events."""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import TYPEID_LENGTH, Base, StringEnum
from api.permissions import ResourceType
from nokodo_ai.utils.typeid import TypeID


class AccessRevision(Base):
	"""append-only resolved-access revision; TypeIDs are never reused."""

	__tablename__ = "access_revisions"

	resource_type: Mapped[ResourceType] = mapped_column(
		StringEnum(ResourceType),
		primary_key=True,
	)
	resource_id: Mapped[TypeID] = mapped_column(
		String(TYPEID_LENGTH),
		primary_key=True,
	)
	revision: Mapped[int] = mapped_column(Integer, default=0)
