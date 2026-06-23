"""SQL predicates for resource authorization."""

from __future__ import annotations

from sqlalchemy import exists, literal, or_, select, true
from sqlalchemy.sql import ColumnElement

from api.models.access_rule import AccessLevel, AccessRule
from api.permissions import ResourceType
from api.v1.service.auth import Principal
from api.v1.service.authorization.config import RESOURCE_CONFIG, allowed_levels
from api.v1.service.authorization.inheritance import inherited_resource_access_predicate


def _false() -> ColumnElement[bool]:
	"""return a SQL literal False."""
	return literal(False)


def _direct_resource_access_predicate(
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel,
) -> ColumnElement[bool]:
	config = RESOURCE_CONFIG[resource_type]
	matching_levels = allowed_levels(required_level)
	user_id = principal.user.id
	rule_fk = config.rule_fk
	id_col = config.id_col
	owner_fk = config.owner_fk

	user_rule = exists(
		select(1).where(
			rule_fk == id_col,
			AccessRule.subject_user_id == user_id,
			AccessRule.level.in_(matching_levels),
		)
	)

	group_rule = (
		exists(
			select(1).where(
				rule_fk == id_col,
				AccessRule.subject_group_id.in_(principal.group_ids),
				AccessRule.level.in_(matching_levels),
			)
		)
		if principal.group_ids
		else _false()
	)

	role_rule = (
		exists(
			select(1).where(
				rule_fk == id_col,
				AccessRule.subject_role_id.in_(principal.role_ids),
				AccessRule.level.in_(matching_levels),
			)
		)
		if principal.role_ids
		else _false()
	)

	public_rule = exists(
		select(1).where(
			rule_fk == id_col,
			AccessRule.subject_user_id.is_(None),
			AccessRule.subject_group_id.is_(None),
			AccessRule.subject_role_id.is_(None),
			AccessRule.level.in_(matching_levels),
		)
	)

	if owner_fk is not None:
		direct_access = or_(
			owner_fk == user_id, user_rule, group_rule, role_rule, public_rule
		)
	else:
		direct_access = or_(user_rule, group_rule, role_rule, public_rule)

	if principal.has_default_access(resource_type, required_level):
		direct_access = or_(direct_access, true())

	return direct_access


def resource_access_predicate(
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
) -> ColumnElement[bool]:
	"""return a SQL predicate limiting resources to those accessible by principal."""
	if principal.is_admin:
		return true()

	base_access = _direct_resource_access_predicate(
		principal,
		resource_type,
		required_level,
	)
	inherited_access = inherited_resource_access_predicate(
		principal,
		resource_type,
		required_level,
		resource_access_predicate,
	)
	if inherited_access is not None:
		base_access = or_(base_access, inherited_access)

	return base_access
