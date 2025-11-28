"""Role model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base
from api.models.common import MetadataJSONMixin, UUIDPrimaryKeyMixin


if TYPE_CHECKING:
	from api.models.user import User


class Role(UUIDPrimaryKeyMixin, MetadataJSONMixin, Base):
	"""Role model for permissions and access control."""

	__tablename__ = "roles"

	name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
	permissions: Mapped[list[str]] = mapped_column(JSON, default=list)
	quotas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	priority: Mapped[int] = mapped_column(Integer, default=0)

	users: Mapped[list[User]] = relationship("User", back_populates="role")
