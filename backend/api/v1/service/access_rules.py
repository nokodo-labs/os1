"""service helpers for access rules."""

import logging

import psycopg
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database.post_commit import enqueue_post_commit_action
from api.models.access_rule import AccessLevel, AccessRule
from api.models.user import User
from api.permissions import ActionPermission, ResourceType
from api.schemas.access_rule import (
	AccessLevelResolution,
	AccessRuleCreate,
	AccessRuleEventChange,
	AccessRuleEventSnapshot,
	AccessRuleUpdate,
)
from api.schemas.common import MISSING, MissingType, unwrap_missing
from api.v1.service.authentication import Principal, build_principals
from api.v1.service.authorization import (
	RESOURCE_CONFIG,
	AccessChangeSnapshot,
	AccessGraphCache,
	ACLResourceConfig,
	apply_metadata_write,
	build_access_change_events,
	capture_access_change,
	get_effective_access_level,
	invalidate_accessible_users_for_refs,
	level_satisfies,
	require_permission,
	require_resource_access,
)
from api.v1.service.authorization.config import is_acl_resource_config
from api.v1.service.events import fanout_event
from api.v1.service.vectorize import (
	sync_resource_refs_vector_acl,
)
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _acl_resource_config(resource_type: ResourceType) -> ACLResourceConfig:
	config = RESOURCE_CONFIG[resource_type]
	if not is_acl_resource_config(config):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail=f"{resource_type.value} does not have independent access rules",
		)
	return config


def _rule_snapshot(rule: AccessRule) -> AccessRuleEventSnapshot:
	"""project one rule to the stable event-safe ACL shape."""
	return AccessRuleEventSnapshot.model_validate(rule)


def _rule_snapshots(rules: list[AccessRule]) -> list[AccessRuleEventSnapshot]:
	"""project an ordered ACL to the canonical event-safe shape."""
	return [_rule_snapshot(rule) for rule in rules]


def _rule_changes(
	before: list[AccessRuleEventSnapshot],
	after: list[AccessRuleEventSnapshot],
) -> list[AccessRuleEventChange]:
	"""derive deterministic per-rule deltas from serialized ACL snapshots."""
	before_by_id = {rule.id: rule for rule in before}
	after_by_id = {rule.id: rule for rule in after}
	return [
		AccessRuleEventChange(
			before=before_by_id.get(rule_id),
			after=after_by_id.get(rule_id),
		)
		for rule_id in dict.fromkeys([*before_by_id, *after_by_id])
		if before_by_id.get(rule_id) != after_by_id.get(rule_id)
	]


def _is_access_relevant(change: AccessRuleEventChange) -> bool:
	"""whether one rule delta can move who can do what.

	a rule appearing or disappearing always can. otherwise only the level and
	the subject columns matter - `order_index` is display order, and
	`resolve_effective_level` reads every matching rule and takes the highest,
	so their sequence changes nothing.
	"""
	if change.before is None or change.after is None:
		return True
	return (
		change.before.level,
		change.before.subject_user_id,
		change.before.subject_group_id,
		change.before.subject_role_id,
	) != (
		change.after.level,
		change.after.subject_user_id,
		change.after.subject_group_id,
		change.after.subject_role_id,
	)


async def _begin_rules_mutation(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> tuple[list[AccessRule], list[AccessRuleEventSnapshot], AccessChangeSnapshot]:
	"""serialize one resource's ACL mutation and capture its canonical baseline."""
	_acl_resource_config(resource_type)
	# root only: descendants are repaired by ancestor validation and the ACL
	# staleness sweep rather than by walking the subtree on every edit.
	access_change = await capture_access_change(
		[(resource_type, resource_id)],
		session,
	)
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	return (
		existing,
		_rule_snapshots(existing),
		access_change,
	)


async def _require_locked_admin(
	resource_type: ResourceType,
	resource_id: TypeID,
	principal: Principal,
	rules: list[AccessRule],
	session: AsyncSession,
) -> None:
	"""revalidate ACL administration after acquiring mutation locks."""
	config = _acl_resource_config(resource_type)
	owner_id = (
		await session.scalar(
			select(config.owner_fk).where(config.id_col == resource_id)
		)
		if config.owner_fk is not None
		else None
	)
	effective = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		owner_id=owner_id,
		rules=rules,
	)
	if effective is None or not level_satisfies(effective, AccessLevel.ADMIN):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)


def _subject_key(
	user_id: TypeID | None,
	group_id: TypeID | None,
	role_id: TypeID | None,
) -> str:
	"""stable access-rule subject identity used for deduplication."""
	if user_id is not None:
		return f"user:{user_id}"
	if group_id is not None:
		return f"group:{group_id}"
	if role_id is not None:
		return f"role:{role_id}"
	return "public"


def _is_link_rule(rule: AccessRule) -> bool:
	return (
		rule.subject_user_id is None
		and rule.subject_group_id is None
		and rule.subject_role_id is None
	)


def _rule_from_snapshot(
	rules: list[AccessRule],
	rule_id: TypeID,
) -> AccessRule | None:
	return next((rule for rule in rules if rule.id == rule_id), None)


def _apply_resource_fk(
	access_rule: AccessRule,
	resource_type: ResourceType,
	resource_id: TypeID,
) -> None:
	"""set the correct resource FK on an access rule by resource type.

	the column comes from the resource registry, so a new resource type is
	wired here automatically instead of silently writing no FK.
	"""
	setattr(access_rule, _acl_resource_config(resource_type).rule_fk.key, resource_id)


async def _list_rules_for_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> list[AccessRule]:
	"""list all access rules for a specific resource, ordered by order_index."""
	config = _acl_resource_config(resource_type)

	stmt = (
		select(AccessRule)
		.where(config.rule_fk == resource_id)
		.order_by(AccessRule.order_index, AccessRule.id)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_access_rules(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> list[AccessRule]:
	"""list access rules for a resource.

	read visibility is per resource type (``ResourceConfig.acl_list_visibility``,
	default ADMIN); mutation is always ADMIN. fetches rules once for both the
	check and the return value, avoiding a redundant DB round-trip.
	"""
	config = _acl_resource_config(resource_type)
	stmt = select(config.id_col)
	if config.owner_fk is not None:
		stmt = select(config.id_col, config.owner_fk)
	stmt = stmt.where(config.id_col == resource_id)

	result = await session.execute(stmt)
	row = result.one_or_none()
	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	# the row is already loaded, so None (not MISSING) keeps the resolver from
	# re-running the existence query for owner-less resource types.
	owner_id: TypeID | None | MissingType = (
		row[1] if config.owner_fk is not None else None
	)

	rules = await _list_rules_for_resource(resource_type, resource_id, session)

	# the link arm is deliberately excluded: a link visitor must never enumerate
	# the named subjects of a resource.
	effective = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		owner_id=owner_id,
		rules=rules,
	)
	required = config.acl_list_visibility
	if effective is None or not level_satisfies(effective, required):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	return rules


async def resolve_access_levels(
	resource_type: ResourceType,
	resource_id: TypeID,
	subject_user_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
) -> list[AccessLevelResolution]:
	"""resolve effective access levels for explicit users on a resource.

	this endpoint answers EFFECTIVE ACCESS - "what can user X actually do
	here" - with inheritance and the link arm included, because that is the
	truth about X. it is deliberately NOT the place to read sharing
	configuration: who was granted what, and whether a link share exists, are
	answered by ``list_access_rules`` under ``acl_list_visibility``. a share
	sheet that needs to tell "alice was granted reader" from "alice is a reader
	because the resource is link-shared" reads the RULE LIST for that, never
	this.

	the gate: the caller holds a named grant, or asks only about themselves.
	the PAYLOAD never depends on which of those is true - a level is the same
	level whoever asks - only the gate does.

	accepted disclosure, stated because it is a real one: on a link-shared
	resource, a named-grant holder gets ``reader`` for an existing active user
	id and ``null`` for a nonexistent or inactive one, which confirms a known
	id exists. ids are TypeIDs, so enumeration is impractical and confirming a
	known id is the whole of it.
	"""
	requested_user_ids = _unique_typeids(subject_user_ids)
	if not requested_user_ids:
		# refused here, not by the request schema: an empty request would skip
		# every authorization check while the owner lookup still leaks 200 vs 404.
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="at least one user must be requested",
		)
	# self-only requests are gated by identity alone, so the existence probe
	# below must not run first for them either.
	self_only = set(requested_user_ids) <= {principal.user.id}

	owner_id = await _get_resource_owner_id(resource_type, resource_id, session)
	rules = await _list_rules_for_resource(resource_type, resource_id, session)
	# naming OTHER users requires a NAMED grant (the link arm is excluded),
	# while asking only about yourself needs no grant at all.
	requester_level = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		owner_id=owner_id,
		rules=rules,
		include_link_access=self_only,
	)
	if requester_level is None:
		if self_only:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"{resource_type.value} not found",
			)
		# two tracks: a caller who can already see the resource is refused a
		# capability (403); a caller who cannot must not learn it exists (404).
		link_level = await get_effective_access_level(
			session,
			principal,
			resource_type,
			resource_id,
			owner_id=owner_id,
			rules=rules,
			include_link_access=True,
		)
		if link_level is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"{resource_type.value} not found",
			)
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	target_principals: dict[TypeID, Principal] = {principal.user.id: principal}
	other_user_ids = [
		user_id for user_id in requested_user_ids if user_id != principal.user.id
	]
	users = list(
		await session.scalars(
			select(User)
			.options(selectinload(User.roles))
			.where(
				User.id.in_(other_user_ids),
				User.is_active.is_(True),
			)
		)
	)
	target_principals.update(await build_principals(users, session))
	graph_cache = AccessGraphCache()
	return [
		AccessLevelResolution(
			resource_type=resource_type,
			resource_id=resource_id,
			subject="user",
			user_id=user_id,
			level=(
				await get_effective_access_level(
					session,
					target_principal,
					resource_type,
					resource_id,
					owner_id=owner_id,
					rules=rules,
					include_link_access=True,
					graph_cache=graph_cache,
				)
				if (target_principal := target_principals.get(user_id)) is not None
				else None
			),
		)
		for user_id in requested_user_ids
	]


async def _get_resource_owner_id(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> TypeID | None | MissingType:
	config = _acl_resource_config(resource_type)
	stmt = select(config.id_col)
	if config.owner_fk is not None:
		stmt = select(config.id_col, config.owner_fk)
	stmt = stmt.where(config.id_col == resource_id)

	result = await session.execute(stmt)
	row = result.one_or_none()
	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)
	if config.owner_fk is None:
		return None
	return row[1]


def _unique_typeids(values: list[TypeID]) -> list[TypeID]:
	return list(dict.fromkeys(values))


async def set_access_rules(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
	principal: Principal,
) -> list[AccessRule]:
	"""
	replace all access rules for a resource.

	requires admin access on the resource.
	subject FK validity is enforced by the database.
	"""
	await require_resource_access(
		resource_id,
		session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)
	if any(rule.subject_role_id is not None for rule in rules):
		require_permission(principal, ActionPermission.ROLES_MANAGE)
	return await _set_rules_impl(
		resource_type,
		resource_id,
		rules,
		session,
		actor_user_id=principal.user.id,
		authorize_principal=principal,
	)


async def set_access_rules_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
) -> list[AccessRule]:
	"""replace all access rules for a resource without authorization checks.

	the caller is responsible for verifying that the principal has
	appropriate permissions before calling this function.
	subject FK validity is enforced by the database.
	"""
	return await _set_rules_impl(resource_type, resource_id, rules, session)


async def create_access_rule(
	resource_type: ResourceType,
	resource_id: TypeID,
	rule: AccessRuleCreate,
	session: AsyncSession,
	principal: Principal,
) -> AccessRule:
	"""create one access rule for a resource."""
	await require_resource_access(
		resource_id,
		session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)
	if rule.subject_role_id is not None:
		require_permission(principal, ActionPermission.ROLES_MANAGE)
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	await _require_locked_admin(
		resource_type, resource_id, principal, existing, session
	)
	rule_key = _subject_key(
		rule.subject_user_id,
		rule.subject_group_id,
		rule.subject_role_id,
	)
	if any(
		_subject_key(
			existing_rule.subject_user_id,
			existing_rule.subject_group_id,
			existing_rule.subject_role_id,
		)
		== rule_key
		for existing_rule in existing
	):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="duplicate subject in access rules",
		)
	access_rule = AccessRule(
		subject_user_id=rule.subject_user_id,
		subject_group_id=rule.subject_group_id,
		subject_role_id=rule.subject_role_id,
		level=rule.level,
		order_index=unwrap_missing(rule.order_index, _next_order_index(existing)),
	)
	access_rule.set_metadata(public=unwrap_missing(rule.metadata, {}))
	_apply_resource_fk(access_rule, resource_type, resource_id)
	session.add(access_rule)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		principal.user.id,
	)
	await session.refresh(access_rule)
	return access_rule


async def grant_user_access_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
	level: AccessLevel = AccessLevel.EDITOR,
	actor_user_id: TypeID | None = None,
) -> AccessRule:
	"""upsert a user access rule for a resource without authz checks.

	creates or re-levels the rule; an unchanged level is a no-op. this helper
	flushes but does not commit. the caller owns the transaction boundary and
	must run queued post-commit actions after a successful explicit commit.
	the caller is also responsible for verifying the principal may grant.
	"""
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	target = next((rule for rule in existing if rule.subject_user_id == user_id), None)
	if target is not None and target.level == level:
		return target
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	access_rule = next(
		(rule for rule in existing if rule.subject_user_id == user_id), None
	)
	if access_rule is None:
		access_rule = AccessRule(
			subject_user_id=user_id,
			level=level,
			order_index=_next_order_index(existing),
		)
		_apply_resource_fk(access_rule, resource_type, resource_id)
		session.add(access_rule)
	else:
		access_rule.level = level
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)
	await session.refresh(access_rule)
	return access_rule


async def grant_subject_access_batch_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	user_grants: dict[TypeID, AccessLevel],
	group_grants: dict[TypeID, AccessLevel],
	session: AsyncSession,
	actor_user_id: TypeID | None = None,
) -> None:
	"""upsert user and group grants through one locked access snapshot."""
	if not user_grants and not group_grants:
		return
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	existing_users = {
		rule.subject_user_id: rule
		for rule in existing
		if rule.subject_user_id is not None
	}
	existing_groups = {
		rule.subject_group_id: rule
		for rule in existing
		if rule.subject_group_id is not None
	}
	if all(
		existing_users.get(subject_id) is not None
		and existing_users[subject_id].level == level
		for subject_id, level in user_grants.items()
	) and all(
		existing_groups.get(subject_id) is not None
		and existing_groups[subject_id].level == level
		for subject_id, level in group_grants.items()
	):
		return
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	existing_users = {
		rule.subject_user_id: rule
		for rule in existing
		if rule.subject_user_id is not None
	}
	existing_groups = {
		rule.subject_group_id: rule
		for rule in existing
		if rule.subject_group_id is not None
	}
	next_order_index = _next_order_index(existing)
	for subject_id, level in user_grants.items():
		rule = existing_users.get(subject_id)
		if rule is None:
			rule = AccessRule(
				subject_user_id=subject_id,
				level=level,
				order_index=next_order_index,
			)
			next_order_index += 1
			_apply_resource_fk(rule, resource_type, resource_id)
			session.add(rule)
		else:
			rule.level = level
	for subject_id, level in group_grants.items():
		rule = existing_groups.get(subject_id)
		if rule is None:
			rule = AccessRule(
				subject_group_id=subject_id,
				level=level,
				order_index=next_order_index,
			)
			next_order_index += 1
			_apply_resource_fk(rule, resource_type, resource_id)
			session.add(rule)
		else:
			rule.level = level
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)


async def revoke_user_access_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
	actor_user_id: TypeID | None = None,
) -> None:
	"""delete a user's access rule for a resource if present, no authz checks.

	this helper flushes but does not commit. the caller owns the transaction
	boundary and must run queued post-commit actions after a successful explicit
	commit. the caller is responsible for verifying the principal may revoke.
	"""
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	target = next((r for r in existing if r.subject_user_id == user_id), None)
	if target is None:
		return
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	target = next((r for r in existing if r.subject_user_id == user_id), None)
	if target is None:
		return
	await session.delete(target)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)


async def grant_group_access_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	group_id: TypeID,
	session: AsyncSession,
	level: AccessLevel = AccessLevel.EDITOR,
	actor_user_id: TypeID | None = None,
) -> AccessRule:
	"""upsert a group access rule for a resource without authz checks.

	grants the resource to the group's current members live. this helper flushes
	but does not commit. the caller owns the transaction boundary and must run
	queued post-commit actions after a successful explicit commit. the caller is
	responsible for verifying the principal may grant access.
	"""
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	target = next(
		(rule for rule in existing if rule.subject_group_id == group_id), None
	)
	if target is not None and target.level == level:
		return target
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	access_rule = next(
		(rule for rule in existing if rule.subject_group_id == group_id), None
	)
	if access_rule is None:
		access_rule = AccessRule(
			subject_group_id=group_id,
			level=level,
			order_index=_next_order_index(existing),
		)
		_apply_resource_fk(access_rule, resource_type, resource_id)
		session.add(access_rule)
	else:
		access_rule.level = level
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)
	await session.refresh(access_rule)
	return access_rule


async def revoke_group_access_unchecked(
	resource_type: ResourceType,
	resource_id: TypeID,
	group_id: TypeID,
	session: AsyncSession,
	actor_user_id: TypeID | None = None,
) -> None:
	"""delete a group's access rule for a resource if present, no authz checks.

	this helper flushes but does not commit. the caller owns the transaction
	boundary and must run queued post-commit actions after a successful explicit
	commit. the caller is responsible for verifying the principal may revoke.
	"""
	existing = await _list_rules_for_resource(resource_type, resource_id, session)
	target = next((r for r in existing if r.subject_group_id == group_id), None)
	if target is None:
		return
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	target = next((r for r in existing if r.subject_group_id == group_id), None)
	if target is None:
		return
	await session.delete(target)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)


async def get_access_rule(
	resource_type: ResourceType,
	resource_id: TypeID,
	rule_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> AccessRule:
	"""get one access rule for a resource."""
	rules = await list_access_rules(resource_type, resource_id, session, principal)
	access_rule = _rule_from_snapshot(rules, rule_id)
	if access_rule is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="access rule not found",
		)
	return access_rule


async def update_access_rule(
	resource_type: ResourceType,
	resource_id: TypeID,
	rule_id: TypeID,
	update: AccessRuleUpdate,
	session: AsyncSession,
	principal: Principal,
) -> AccessRule:
	"""update one access rule for a resource."""
	await require_resource_access(
		resource_id,
		session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)
	# fail fast before the potentially blocking lock; the locked snapshot below
	# remains authoritative if another writer changes the rule meanwhile.
	requested_rule = await _get_rule_for_resource(
		resource_type, resource_id, rule_id, session
	)
	if requested_rule.subject_role_id is not None:
		require_permission(principal, ActionPermission.ROLES_MANAGE)
	if (
		_is_link_rule(requested_rule)
		and update.level is not MISSING
		and update.level != AccessLevel.READER
	):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="link access rules must grant reader access",
		)
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	await _require_locked_admin(
		resource_type, resource_id, principal, existing, session
	)
	access_rule = _rule_from_snapshot(existing, rule_id)
	if access_rule is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="access rule not found",
		)
	if isinstance(update.level, AccessLevel):
		access_rule.level = update.level
	if isinstance(update.order_index, int):
		access_rule.order_index = update.order_index
	apply_metadata_write(access_rule, update.metadata)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		principal.user.id,
	)
	await session.refresh(access_rule)
	return access_rule


async def delete_access_rule(
	resource_type: ResourceType,
	resource_id: TypeID,
	rule_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete one access rule for a resource."""
	await require_resource_access(
		resource_id,
		session,
		principal,
		resource_type,
		required_level=AccessLevel.ADMIN,
	)
	# fail fast before the potentially blocking lock; the locked snapshot below
	# remains authoritative if another writer changes the rule meanwhile.
	requested_rule = await _get_rule_for_resource(
		resource_type, resource_id, rule_id, session
	)
	if requested_rule.subject_role_id is not None:
		require_permission(principal, ActionPermission.ROLES_MANAGE)
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	await _require_locked_admin(
		resource_type, resource_id, principal, existing, session
	)
	access_rule = _rule_from_snapshot(existing, rule_id)
	if access_rule is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="access rule not found",
		)
	await session.delete(access_rule)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		principal.user.id,
	)


async def _set_rules_impl(
	resource_type: ResourceType,
	resource_id: TypeID,
	rules: list[AccessRuleCreate],
	session: AsyncSession,
	actor_user_id: TypeID | None = None,
	authorize_principal: Principal | None = None,
) -> list[AccessRule]:
	"""shared implementation for replacing access rules on a resource."""
	existing, before_rules, access_change = await _begin_rules_mutation(
		resource_type, resource_id, session
	)
	if authorize_principal is not None:
		await _require_locked_admin(
			resource_type,
			resource_id,
			authorize_principal,
			existing,
			session,
		)
		desired_role_ids = {
			rule.subject_role_id for rule in rules if rule.subject_role_id is not None
		}
		if desired_role_ids or any(
			existing_rule.subject_role_id is not None
			and existing_rule.subject_role_id not in desired_role_ids
			for existing_rule in existing
		):
			require_permission(authorize_principal, ActionPermission.ROLES_MANAGE)
	existing_by_key: dict[str, AccessRule] = {}
	for existing_rule in existing:
		key = _subject_key(
			existing_rule.subject_user_id,
			existing_rule.subject_group_id,
			existing_rule.subject_role_id,
		)
		existing_by_key[key] = existing_rule
	desired_keys: set[str] = set()

	for i, rule in enumerate(rules):
		rule_key = _subject_key(
			rule.subject_user_id,
			rule.subject_group_id,
			rule.subject_role_id,
		)
		if rule_key in desired_keys:
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="duplicate subject in access rules",
			)
		desired_keys.add(rule_key)

		access_rule = existing_by_key.get(rule_key)
		if access_rule is None:
			access_rule = AccessRule(
				subject_user_id=rule.subject_user_id,
				subject_group_id=rule.subject_group_id,
				subject_role_id=rule.subject_role_id,
				level=rule.level,
				order_index=unwrap_missing(rule.order_index, i),
			)
			access_rule.set_metadata(public=unwrap_missing(rule.metadata, {}))
			_apply_resource_fk(access_rule, resource_type, resource_id)
			session.add(access_rule)
		else:
			access_rule.level = rule.level
			access_rule.order_index = unwrap_missing(rule.order_index, i)
			if rule.metadata is not MISSING:
				access_rule.set_metadata(public=unwrap_missing(rule.metadata, {}))

	# remove rules no longer in the list
	for key, existing_rule in existing_by_key.items():
		if key not in desired_keys:
			await session.delete(existing_rule)
	await _commit_rules_mutation(
		resource_type,
		resource_id,
		session,
		access_change,
		before_rules,
		actor_user_id,
	)

	return await _list_rules_for_resource(resource_type, resource_id, session)


def _next_order_index(rules: list[AccessRule]) -> int:
	"""return an order index after every existing rule."""
	return max((rule.order_index for rule in rules), default=-1) + 1


async def _get_rule_for_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
	rule_id: TypeID,
	session: AsyncSession,
) -> AccessRule:
	config = _acl_resource_config(resource_type)
	result = await session.execute(
		select(AccessRule).where(
			AccessRule.id == rule_id,
			config.rule_fk == resource_id,
		)
	)
	access_rule = result.scalar_one_or_none()
	if access_rule is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="access rule not found",
		)
	return access_rule


async def _commit_rules_mutation(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	access_change: AccessChangeSnapshot,
	before_rules: list[AccessRuleEventSnapshot],
	actor_user_id: TypeID | None,
) -> None:
	config = _acl_resource_config(resource_type)
	try:
		await session.flush()
		after_rules = _rule_snapshots(
			await _list_rules_for_resource(
				resource_type,
				resource_id,
				session,
			)
		)
		changes = _rule_changes(before_rules, after_rules)
		prepared_events = []
		if changes:
			owner_user_id = (
				await session.scalar(
					select(config.owner_fk).where(config.id_col == resource_id)
				)
				if config.owner_fk is not None
				else None
			)
			prepared_events = await build_access_change_events(
				access_change,
				session,
				actor_user_id=actor_user_id,
				data_by_resource={
					(resource_type, resource_id): {
						"owner_user_id": (
							str(owner_user_id) if owner_user_id is not None else None
						),
						"actor_user_id": (
							str(actor_user_id) if actor_user_id is not None else None
						),
						"changes": [
							change.model_dump(mode="json") for change in changes
						],
					},
				},
				# only ACCESS-RELEVANT deltas force an event: `order_index` is
				# display order, so a reorder must not bump the revision and resync.
				forced_resource_refs=(
					{(resource_type, resource_id)}
					if any(_is_access_relevant(change) for change in changes)
					else set()
				),
			)
	except IntegrityError as exc:
		constraint_name = (
			exc.orig.diag.constraint_name
			if isinstance(exc.orig, psycopg.Error)
			else None
		)
		if constraint_name == "uq_access_rule_subject_resource":
			logger.info("duplicate access-rule subject rejected")
			raise HTTPException(
				status_code=status.HTTP_409_CONFLICT,
				detail="duplicate subject in access rules",
			) from exc
		logger.exception("access rule mutation violated a database constraint")
		if constraint_name is None or not (
			constraint_name.startswith("access_rules_")
			or constraint_name.startswith("ck_access_rules_")
			or constraint_name.startswith("fk_access_rules_")
		):
			raise
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="invalid access rule reference",
		) from exc
	# an order-only edit changes nobody's access, so it earns neither a cache
	# invalidation nor a vector ACL resync.
	if not any(_is_access_relevant(change) for change in changes):
		return

	async def invalidate_after_commit(db: AsyncSession) -> None:
		_ = db
		await invalidate_accessible_users_for_refs(access_change.affected_resource_refs)

	async def sync_vectors_after_commit(db: AsyncSession) -> None:
		await sync_resource_refs_vector_acl(
			access_change.affected_resource_refs,
			db,
		)

	async def fanout_after_commit(db: AsyncSession) -> None:
		_ = db
		for prepared in prepared_events:
			await fanout_event(prepared.event, recipient_ids=prepared.recipient_ids)

	enqueue_post_commit_action(session, invalidate_after_commit)
	enqueue_post_commit_action(session, fanout_after_commit)
	enqueue_post_commit_action(session, sync_vectors_after_commit)
