"""access rule schemas."""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from api.models.access_rule import AccessLevel
from api.schemas.common import MetadataModel, ORMModel, TimestampedModel
from nokodo_ai.utils.typeid import TypeID


class AccessRuleCreate(MetadataModel):
	"""payload for creating/updating access rules on a resource."""

	subject_user_id: TypeID | None = None
	subject_group_id: TypeID | None = None
	subject_role_id: TypeID | None = None
	level: AccessLevel = Field(default=AccessLevel.READER)
	order_index: int = Field(default=0, ge=0)

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
		return self


class AccessRuleResponse(MetadataModel, TimestampedModel, ORMModel):
	"""response schema for an access rule."""

	id: TypeID
	subject_user_id: TypeID | None = None
	subject_group_id: TypeID | None = None
	subject_role_id: TypeID | None = None
	level: AccessLevel
	order_index: int

	# resource IDs (only one set)
	thread_id: TypeID | None = None
	project_id: TypeID | None = None
	agent_id: TypeID | None = None
	note_id: TypeID | None = None
	memory_id: TypeID | None = None
	task_id: TypeID | None = None
	file_id: TypeID | None = None
	plugin_id: TypeID | None = None
	prompt_id: TypeID | None = None
	group_id: TypeID | None = None
	reminder_list_id: TypeID | None = None
	calendar_id: TypeID | None = None


class AccessRulesUpdate(ORMModel):
	"""payload for replacing all access rules on a resource."""

	rules: list[AccessRuleCreate] = Field(default_factory=list)


class AccessRulesResponse(ORMModel):
	"""response containing all access rules for a resource."""

	rules: list[AccessRuleResponse] = Field(default_factory=list)
