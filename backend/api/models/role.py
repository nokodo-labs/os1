"""role model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base
from api.models.many_to_many import user_role_association
from api.models.mixins import MetadataJSONMixin, TimestampMixin, TypeIDPrimaryKeyMixin
from api.permissions import DefaultPermissions


if TYPE_CHECKING:
	from api.models.user import User


class Role(TypeIDPrimaryKeyMixin, TimestampMixin, MetadataJSONMixin, Base):
	"""role model for permissions and resource access defaults."""

	__tablename__ = "roles"
	__typeid_prefix__ = "role"

	name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
	description: Mapped[str | None] = mapped_column(Text)
	quotas: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
	priority: Mapped[int] = mapped_column(Integer, default=0)

	# typed default permissions — resource access levels + action permissions
	default_permissions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

	users: Mapped[list[User]] = relationship(
		"User",
		secondary=user_role_association,
		back_populates="roles",
	)

	def get_default_permissions(self) -> DefaultPermissions:
		"""deserialize the JSON column into a typed DefaultPermissions model."""
		return DefaultPermissions.model_validate(self.default_permissions)

	def set_default_permissions(self, value: DefaultPermissions) -> None:
		"""serialize a DefaultPermissions model into the JSON column."""
		self.default_permissions = value.model_dump(
			mode="json",
			exclude_none=True,
		)
