"""access rule schemas."""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from api.permissions import AccessLevel, ResourceType
from api.schemas.common import (
	MISSING,
	ForbidExtraModel,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	ORMModel,
	TimestampedModel,
)
from nokodo_ai.utils.typeid import TypeID


class ResourceAccessListFilters(ForbidExtraModel):
	"""common effective-access filters for ACL resource listings."""

	access_relationship: Literal["owned", "shared"] | None = None
	resolved_access_level: AccessLevel | None = None


class AccessRuleCreate(MetadataUpdateModel, ForbidExtraModel):
	"""payload for creating/updating access rules on a resource."""

	subject_user_id: TypeID | None = None
	subject_group_id: TypeID | None = None
	subject_role_id: TypeID | None = None
	level: AccessLevel = Field(default=AccessLevel.READER)
	order_index: int | MissingType = Field(default=MISSING, ge=0)

	@model_validator(mode="after")
	def _validate_subject(self) -> AccessRuleCreate:
		principal_fields = [
			self.subject_user_id,
			self.subject_group_id,
			self.subject_role_id,
		]
		principal_count = sum(1 for value in principal_fields if value is not None)
		if principal_count > 1:
			raise PydanticCustomError(
				"access_rule_subject",
				"only one subject field may be set",
			)
		if principal_count == 0 and self.level != AccessLevel.READER:
			raise PydanticCustomError(
				"access_rule_link_level",
				"link access rules must grant reader access",
			)
		return self


class AccessRuleResponse(MetadataModel, TimestampedModel, ORMModel):
	"""response schema for an access rule."""

	id: TypeID
	subject_user_id: TypeID | None = None
	subject_group_id: TypeID | None = None
	subject_role_id: TypeID | None = None
	level: AccessLevel
	order_index: int


class AccessRuleUpdate(MetadataUpdateModel, ForbidExtraModel):
	"""payload for updating one access rule on a resource."""

	level: AccessLevel | MissingType = MISSING
	order_index: int | MissingType = Field(default=MISSING, ge=0)


class AccessRuleEventSnapshot(ORMModel):
	"""access-rule state exposed in a canonical access event."""

	id: TypeID
	subject_user_id: TypeID | None = None
	subject_group_id: TypeID | None = None
	subject_role_id: TypeID | None = None
	level: AccessLevel
	order_index: int


class AccessRuleEventChange(ORMModel):
	"""one access-rule transition within a revisioned ACL mutation."""

	before: AccessRuleEventSnapshot | None = None
	after: AccessRuleEventSnapshot | None = None


class AccessLevelResolveRequest(ForbidExtraModel):
	"""request explicit effective access levels for a resource."""

	subject_user_ids: list[TypeID] = Field(default_factory=list, max_length=100)
	link: bool = False

	@model_validator(mode="after")
	def _require_subject(self) -> AccessLevelResolveRequest:
		if not self.subject_user_ids and not self.link:
			raise PydanticCustomError(
				"access_level_resolve_subject",
				"at least one user or link must be requested",
			)
		return self


class AccessLevelResolution(ORMModel):
	"""effective access level for one subject on one resource."""

	resource_type: ResourceType
	resource_id: TypeID
	subject: Literal["user", "link"] = "user"
	user_id: TypeID | None = None
	level: AccessLevel | None = None
