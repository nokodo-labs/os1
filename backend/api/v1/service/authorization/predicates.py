"""SQL predicates for resource authorization.

recursion here is bounded by DEPTH ALONE - ``inherited_resource_access_predicate``
returns None at ``MAX_INHERITANCE_DEPTH`` and there is no cycle guard. that is
sound because a predicate is a pure tree: unlike the two resolvers, nothing is
memoised across depths in a way a repeat could truncate, and the depth bound
terminates the build. it does mean a cycle in the transitive link graph would
build an exhaustive fan-out rather than break, which is what
``test_the_depth_bound_is_slack_not_a_live_limit`` exists to keep unreachable.
"""

from collections.abc import Callable
from typing import NamedTuple

from sqlalchemy import and_, exists, false, not_, or_, select, true
from sqlalchemy.sql import ColumnElement, Select

from api.models.access_rule import AccessLevel, AccessRule
from api.models.group import GroupMembership
from api.models.many_to_many import user_role_association
from api.models.role import Role
from api.models.user import User
from api.permissions import (
	DEFAULT_ACCESS_RESOURCE_TYPES,
	RESOURCE_MANAGE_PERMISSION,
	ResourceType,
	permission_satisfied_by,
	wildcards_granting,
)
from api.settings import settings
from api.v1.service.authentication import Principal
from api.v1.service.authorization.config import (
	RESOURCE_CONFIG,
	allowed_levels,
	is_acl_resource_config,
)
from api.v1.service.authorization.inheritance import (
	AccessTraversalState,
	inherited_resource_access_predicate,
)
from api.v1.service.authorization.types import AccessSubject


class PredicateMemoKey(NamedTuple):
	"""memo key for one built predicate.

	a NamedTuple rather than a bare tuple because the two leading booleans are
	independent flags whose order is not recoverable from a call site: swapping
	them silently hands back the wrong cached predicate, with no error and no
	visible symptom.

	the key carries ``traversal``, which carries the depth. that is deliberate:
	``inherited_resource_access_predicate`` truncates at
	``MAX_INHERITANCE_DEPTH``, so a predicate built with 2 hops of budget left
	is not the predicate a caller with 14 would get.
	"""

	#: resource-derived access only, excluding the operator override. matches
	#: ``resource_derived_access_predicate`` vs ``resource_access_predicate``.
	derived_only: bool
	#: whether subjectless (link) rules are attached. inert above READER.
	include_link_access: bool
	resource_type: ResourceType
	required_level: AccessLevel
	traversal: AccessTraversalState


type PrincipalPredicateMemo = dict[PredicateMemoKey, ColumnElement[bool]]


def direct_resource_access_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	required_level: AccessLevel,
	include_link_access: bool = False,
) -> ColumnElement[bool]:
	"""return the direct-access SQL predicate for one subject."""
	config = RESOURCE_CONFIG[resource_type]
	if not is_acl_resource_config(config):
		return false()
	matching_levels = allowed_levels(required_level)
	user_id = subject.user.id if isinstance(subject, Principal) else subject
	rule_fk = config.rule_fk
	id_col = config.id_col
	owner_fk = config.owner_fk

	if isinstance(subject, Principal):
		group_match = AccessRule.subject_group_id.in_(subject.group_ids)
		role_match = AccessRule.subject_role_id.in_(subject.role_ids)
	else:
		# a column subject needs correlated EXISTS, explicit because
		# auto-correlation reaches only the immediately enclosing select.
		group_match = exists(
			select(1)
			.where(
				GroupMembership.group_id == AccessRule.subject_group_id,
				GroupMembership.user_id == user_id,
			)
			.correlate_except(GroupMembership)
		)
		role_match = exists(
			select(1)
			.where(
				user_role_association.c.role_id == AccessRule.subject_role_id,
				user_role_association.c.user_id == user_id,
			)
			.correlate_except(user_role_association)
		)
	subject_matches: list[ColumnElement[bool]] = [
		AccessRule.subject_user_id == user_id,
		group_match,
		role_match,
	]
	if include_link_access and required_level == AccessLevel.READER:
		subject_matches.append(
			AccessRule.subject_user_id.is_(None)
			& AccessRule.subject_group_id.is_(None)
			& AccessRule.subject_role_id.is_(None)
		)
	rule_access = exists(
		select(1)
		.where(
			rule_fk == id_col,
			or_(*subject_matches),
			AccessRule.level.in_(matching_levels),
		)
		.correlate_except(AccessRule)
	)

	if owner_fk is not None:
		direct_access = or_(owner_fk == user_id, rule_access)
	else:
		direct_access = rule_access

	if (
		isinstance(subject, Principal)
		and owner_fk is not None
		and subject.has_default_access(resource_type, required_level)
	):
		direct_access = or_(direct_access, owner_fk.isnot(None))
	elif (
		not isinstance(subject, Principal)
		and owner_fk is not None
		and resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
	):
		default_levels = allowed_levels(required_level)
		role_default = exists(
			select(1)
			.select_from(user_role_association.join(Role))
			.where(
				user_role_association.c.user_id == user_id,
				Role.default_permissions["resource_access"][resource_type.value]
				.as_string()
				.in_(default_levels),
			)
			.correlate_except(user_role_association, Role)
		)
		global_level = settings.default_permissions.resource_access.get(resource_type)
		direct_access = or_(
			direct_access,
			owner_fk.is_not(None)
			& (true() if global_level in default_levels else role_default),
		)

	return direct_access


def _direct_and_inherited_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	required_level: AccessLevel,
	traversal: AccessTraversalState,
	parent_predicate: Callable[
		[
			AccessSubject,
			ResourceType,
			AccessLevel,
			AccessTraversalState,
			PrincipalPredicateMemo | None,
			bool,
		],
		ColumnElement[bool],
	],
	memo: PrincipalPredicateMemo | None,
	include_link_access: bool,
) -> ColumnElement[bool]:
	"""combine access held on the resource with access earned through a parent."""
	base_access = direct_resource_access_predicate(
		subject,
		resource_type,
		required_level,
		include_link_access=include_link_access,
	)
	inherited_access = inherited_resource_access_predicate(
		subject,
		resource_type,
		required_level,
		lambda nested_subject, nested_type, nested_level, nested_traversal: (
			parent_predicate(
				nested_subject,
				nested_type,
				nested_level,
				nested_traversal,
				memo,
				include_link_access,
			)
		),
		traversal=traversal,
	)
	if inherited_access is None:
		return base_access
	return or_(base_access, inherited_access)


def resource_access_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
	traversal: AccessTraversalState = AccessTraversalState(),
	memo: PrincipalPredicateMemo | None = None,
	include_link_access: bool = False,
) -> ColumnElement[bool]:
	"""return a SQL predicate limiting resources to those accessible by subject.

	``include_link_access`` is IGNORED above READER. a subjectless rule grants
	READER and nothing more, so the arm is attached only at
	``required_level == AccessLevel.READER``, and the inherited arms carry the
	same requirement to parents. passing it at EDITOR or ADMIN cannot change
	the result.
	"""
	if isinstance(subject, Principal):
		if subject.is_resource_operator(resource_type):
			return true()
		if memo is None:
			memo = {}
		key = PredicateMemoKey(
			derived_only=False,
			include_link_access=include_link_access,
			resource_type=resource_type,
			required_level=required_level,
			traversal=traversal,
		)
		if key in memo:
			return memo[key]
		predicate = _direct_and_inherited_predicate(
			subject,
			resource_type,
			required_level,
			traversal,
			resource_access_predicate,
			memo,
			include_link_access,
		)
		memo[key] = predicate
		return predicate
	return or_(
		resource_operator_predicate(subject, resource_type),
		_direct_and_inherited_predicate(
			subject,
			resource_type,
			required_level,
			traversal,
			resource_access_predicate,
			None,
			include_link_access,
		),
	)


def resource_derived_access_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
	traversal: AccessTraversalState = AccessTraversalState(),
	memo: PrincipalPredicateMemo | None = None,
	include_link_access: bool = False,
) -> ColumnElement[bool]:
	"""return access derived from the resource itself, ignoring operators.

	the SQL twin of ``resolve_resource_access_user_ids``: owner, rules and
	defaults on the resource plus whatever a parent confers, but never the
	superuser/manage override - an operator is not a participant.

	``include_link_access`` is IGNORED above READER, for the reason given on
	``resource_access_predicate``.
	"""
	if isinstance(subject, Principal):
		if memo is None:
			memo = {}
		key = PredicateMemoKey(
			derived_only=True,
			include_link_access=include_link_access,
			resource_type=resource_type,
			required_level=required_level,
			traversal=traversal,
		)
		if key in memo:
			return memo[key]
		predicate = _direct_and_inherited_predicate(
			subject,
			resource_type,
			required_level,
			traversal,
			resource_derived_access_predicate,
			memo,
			include_link_access,
		)
		memo[key] = predicate
		return predicate
	return _direct_and_inherited_predicate(
		subject,
		resource_type,
		required_level,
		traversal,
		resource_derived_access_predicate,
		None,
		include_link_access,
	)


def exact_resource_derived_access_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
	level: AccessLevel,
	memo: PrincipalPredicateMemo | None = None,
) -> ColumnElement[bool]:
	"""return whether resource-derived access equals one level."""
	if isinstance(subject, Principal) and memo is None:
		memo = {}
	minimum = resource_derived_access_predicate(
		subject, resource_type, level, memo=memo
	)
	if level == AccessLevel.ADMIN:
		return minimum
	next_level = (
		AccessLevel.EDITOR if level == AccessLevel.READER else AccessLevel.ADMIN
	)
	return and_(
		minimum,
		not_(
			resource_derived_access_predicate(
				subject,
				resource_type,
				next_level,
				memo=memo,
			)
		),
	)


def apply_resource_access_list_filters(
	stmt: Select,
	principal: Principal,
	resource_type: ResourceType,
	access_relationship: str | None,
	resolved_access_level: AccessLevel | None,
) -> Select:
	"""apply resource-derived relationship and exact-level filters."""
	config = RESOURCE_CONFIG[resource_type]
	memo: PrincipalPredicateMemo = {}
	if access_relationship == "owned":
		stmt = stmt.where(
			config.owner_fk == principal.user.id
			if is_acl_resource_config(config) and config.owner_fk is not None
			else false()
		)
	elif access_relationship == "shared":
		shared = resource_derived_access_predicate(
			principal,
			resource_type,
			AccessLevel.READER,
			memo=memo,
		)
		if is_acl_resource_config(config) and config.owner_fk is not None:
			shared = and_(shared, config.owner_fk != principal.user.id)
		stmt = stmt.where(shared)
	if resolved_access_level is not None:
		stmt = stmt.where(
			exact_resource_derived_access_predicate(
				principal,
				resource_type,
				resolved_access_level,
				memo=memo,
			)
		)
	return stmt


def resource_operator_predicate(
	subject: AccessSubject,
	resource_type: ResourceType,
) -> ColumnElement[bool]:
	"""return whether one subject has the resource's operator permission."""
	if isinstance(subject, Principal):
		return true() if subject.is_resource_operator(resource_type) else false()
	manage_permission = RESOURCE_MANAGE_PERMISSION[resource_type]
	permission = manage_permission.value
	# the same grants the python resolver matches, from the one helper
	granting = (permission, *wildcards_granting(permission))
	operator = or_(
		User.is_superuser.is_(True),
		exists(
			select(1)
			.select_from(user_role_association.join(Role))
			.where(
				user_role_association.c.user_id == subject,
				or_(
					*(
						Role.default_permissions["action_permissions"].contains([grant])
						for grant in granting
					)
				),
			)
		),
	)
	if permission_satisfied_by(
		permission,
		settings.default_permissions.action_permissions,
	):
		operator = true()
	return exists(select(1).where(User.id == subject, operator))
