"""acl schemas."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from api.models.acl import AccessRole
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from api.schemas.typeid import TypeID


class AccessControlEntryCreate(MetadataModel):
	"""payload for setting acl entries on a resource."""

	user_id: TypeID | None = None
	group_id: TypeID | None = None
	agent_id: TypeID | None = None

	role: AccessRole = Field(default=AccessRole.VIEWER)

	@model_validator(mode="after")
	def _validate_acl_entry(self) -> AccessControlEntryCreate:
		principal_count = sum(
			1
			for value in (
				self.user_id,
				self.group_id,
				self.agent_id,
			)
			if value is not None
		)
		if principal_count != 1:
			raise PydanticCustomError(
				"acl_principal",
				"Exactly one principal id must be set",
			)
		return self


class AccessControlEntry(MetadataModel, TimestampedModel, ORMModel):
	"""response schema for an ace."""

	id: TypeID
	thread_id: TypeID | None = None
	project_id: TypeID | None = None

	user_id: TypeID | None = None
	group_id: TypeID | None = None
	agent_id: TypeID | None = None

	role: AccessRole
