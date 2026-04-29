"""authorization helpers for the API service layer."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, literal, or_, select, true, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement, Select

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.file import File
from api.models.group import Group, GroupMembership
from api.models.many_to_many import user_role_association
from api.models.memory import Memory
from api.models.note import Note
from api.models.plugin import Plugin
from api.models.project import Project
from api.models.prompt import Prompt
from api.models.reminder import ReminderList
from api.models.role import Role
from api.models.task import Task
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ResourceType
from api.redis import cache
from api.settings import settings
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID


@dataclass(frozen=True, slots=True)
class ResourceConfig:
	"""config for a resource type's access control."""

	id_col: InstrumentedAttribute
	rule_fk: InstrumentedAttribute
	owner_fk: InstrumentedAttribute | None
	deleted_at_col: InstrumentedAttribute | None


# resource type → access control config
RESOURCE_CONFIG: dict[ResourceType, ResourceConfig] = {
	ResourceType.THREAD: ResourceConfig(
		id_col=Thread.id,
		rule_fk=AccessRule.thread_id,
		owner_fk=Thread.owner_id,
		deleted_at_col=Thread.deleted_at,
	),
	ResourceType.PROJECT: ResourceConfig(
		id_col=Project.id,
		rule_fk=AccessRule.project_id,
		owner_fk=Project.owner_id,
		deleted_at_col=None,
	),
	ResourceType.AGENT: ResourceConfig(
		id_col=Agent.id,
		rule_fk=AccessRule.agent_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.NOTE: ResourceConfig(
		id_col=Note.id,
		rule_fk=AccessRule.note_id,
		owner_fk=Note.user_id,
		deleted_at_col=Note.deleted_at,
	),
	ResourceType.MEMORY: ResourceConfig(
		id_col=Memory.id,
		rule_fk=AccessRule.memory_id,
		owner_fk=Memory.user_id,
		deleted_at_col=None,
	),
	ResourceType.TASK: ResourceConfig(
		id_col=Task.id,
		rule_fk=AccessRule.task_id,
		owner_fk=Task.user_id,
		deleted_at_col=None,
	),
	ResourceType.FILE: ResourceConfig(
		id_col=File.id,
		rule_fk=AccessRule.file_id,
		owner_fk=File.owner_id,
		deleted_at_col=File.deleted_at,
	),
	ResourceType.PLUGIN: ResourceConfig(
		id_col=Plugin.id,
		rule_fk=AccessRule.plugin_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.PROMPT: ResourceConfig(
		id_col=Prompt.id,
		rule_fk=AccessRule.prompt_id,
		owner_fk=None,
		deleted_at_col=None,
	),
	ResourceType.GROUP: ResourceConfig(
		id_col=Group.id,
		rule_fk=AccessRule.group_id,
		owner_fk=Group.owner_id,
		deleted_at_col=None,
	),
	ResourceType.REMINDER_LIST: ResourceConfig(
		id_col=ReminderList.id,
		rule_fk=AccessRule.reminder_list_id,
		owner_fk=ReminderList.owner_id,
		deleted_at_col=None,
	),
}


def _level_satisfies(granted: AccessLevel, required: AccessLevel) -> bool:
	"""check if granted access level satisfies the required level."""
	level_order = {AccessLevel.READER: 0, AccessLevel.EDITOR: 1, AccessLevel.ADMIN: 2}
	return level_order[granted] >= level_order[required]


def _allowed_levels(required: AccessLevel) -> tuple[AccessLevel, ...]:
	"""return all access levels that satisfy the required level."""
	match required:
		case AccessLevel.READER:
			return (AccessLevel.READER, AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.EDITOR:
			return (AccessLevel.EDITOR, AccessLevel.ADMIN)
		case AccessLevel.ADMIN:
			return (AccessLevel.ADMIN,)
		case _:
			return (AccessLevel.ADMIN,)


def _false() -> ColumnElement[bool]:
	"""return a SQL literal False."""
	return literal(False)


def resource_access_predicate(
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
	include_deleted: bool = False,
) -> ColumnElement[bool]:
	"""
	return a SQL predicate limiting resources to those accessible by principal.

	access is granted if ANY of the following is true:
	1. principal is superuser
	2. principal owns the resource
	3. an explicit access rule grants sufficient access via:
		- the principal's user ID directly
		- any group the principal belongs to
		- any role the principal has
		- public (everyone)
	4. any of the principal's roles grant a default_permissions entry
		for this resource type at the required level or higher
	"""
	config = RESOURCE_CONFIG[resource_type]

	# visibility filter (soft-deletable resources)
	visibility: ColumnElement[bool]
	if config.deleted_at_col is not None:
		visibility = (
			true()
			if include_deleted and principal.is_admin
			else config.deleted_at_col.is_(None)
		)
	else:
		visibility = true()

	# superuser bypass
	if principal.is_admin:
		return visibility

	allowed_levels = _allowed_levels(required_level)
	user_id = principal.user.id
	rule_fk = config.rule_fk
	id_col = config.id_col
	owner_fk = config.owner_fk

	# user direct rule
	user_rule = exists(
		select(1).where(
			rule_fk == id_col,
			AccessRule.subject_user_id == user_id,
			AccessRule.level.in_(allowed_levels),
		)
	)

	# group rule (any group the user belongs to)
	group_rule = (
		exists(
			select(1).where(
				rule_fk == id_col,
				AccessRule.subject_group_id.in_(principal.group_ids),
				AccessRule.level.in_(allowed_levels),
			)
		)
		if principal.group_ids
		else _false()
	)

	# role rule (any role the user has)
	role_rule = (
		exists(
			select(1).where(
				rule_fk == id_col,
				AccessRule.subject_role_id.in_(principal.role_ids),
				AccessRule.level.in_(allowed_levels),
			)
		)
		if principal.role_ids
		else _false()
	)

	# public rule
	public_rule = exists(
		select(1).where(
			rule_fk == id_col,
			AccessRule.subject_user_id.is_(None),
			AccessRule.subject_group_id.is_(None),
			AccessRule.subject_role_id.is_(None),
			AccessRule.level.in_(allowed_levels),
		)
	)

	if owner_fk is not None:
		base_access = or_(
			owner_fk == user_id, user_rule, group_rule, role_rule, public_rule
		)
	else:
		base_access = or_(user_rule, group_rule, role_rule, public_rule)

	# role + global defaults grant access - shortcut to true()
	if principal.has_default_access(resource_type, required_level):
		base_access = or_(base_access, true())

	return and_(base_access, visibility)


async def list_accessible_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return all user IDs that have at least *required_level* access to a resource.

	results are cached in redis for 5 minutes and tagged by resource for
	invalidation on access rule changes. the long TTL is safe because
	every mutation path that affects the result set (access_rules service,
	role membership, group membership) busts the tag explicitly. the TTL
	is only a safety net for entries that never get explicitly invalidated
	(e.g. after a deleted resource).
	"""
	cache_key = (
		f"accessible_users:{resource_type.value}:{resource_id}:{required_level.value}"
	)

	cached = await cache.get(cache_key)
	if cached is not None and isinstance(cached, list):
		return [TypeID(uid) for uid in cached]

	result = await _list_accessible_user_ids_uncached(
		resource_type, resource_id, session, required_level=required_level
	)
	await cache.set(
		cache_key,
		[str(uid) for uid in result],
		ttl=300,
		tags=[f"resource:{resource_type.value}:{resource_id}"],
	)
	return result


async def invalidate_accessible_users_for_subject(
	subject_kind: Literal["user", "group", "role"],
	subject_id: TypeID,
	session: AsyncSession,
) -> None:
	"""invalidate the ``accessible_users`` cache for every resource that has
	an access rule referencing the given subject.

	called from membership / role mutations so the cache stays accurate
	without resorting to a coarse "invalidate everything" tag. exactly one
	round trip to postgres + one tag invalidation per affected resource.
	"""
	subject_col = {
		"user": AccessRule.subject_user_id,
		"group": AccessRule.subject_group_id,
		"role": AccessRule.subject_role_id,
	}[subject_kind]
	fk_cols = [(cfg.rule_fk, rtype) for rtype, cfg in RESOURCE_CONFIG.items()]
	stmt = select(*[col for col, _ in fk_cols]).where(subject_col == str(subject_id))
	rows = (await session.execute(stmt)).all()
	tags: list[str] = []
	for row in rows:
		for value, (_col, rtype) in zip(row, fk_cols, strict=True):
			if value is not None:
				tags.append(f"resource:{rtype.value}:{value}")
	# fan out the tag invalidations concurrently - each is an independent
	# redis round trip and there is no ordering requirement between them.
	if tags:
		await asyncio.gather(*(cache.invalidate_tag(tag) for tag in tags))


async def _list_accessible_user_ids_uncached(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""uncached implementation of list_accessible_user_ids."""
	config = RESOURCE_CONFIG[resource_type]
	allowed_levels = _allowed_levels(required_level)

	queries: list[Select] = []

	# 1. resource owner
	if config.owner_fk is not None:
		queries.append(select(config.owner_fk).where(config.id_col == resource_id))

	# 2. superusers (implicit admin on everything)
	queries.append(select(User.id).where(User.is_superuser.is_(True)))

	# 3. direct user access rules
	queries.append(
		select(AccessRule.subject_user_id).where(
			config.rule_fk == resource_id,
			AccessRule.subject_user_id.is_not(None),
			AccessRule.level.in_(allowed_levels),
		)
	)

	# 4. group access rules → expand via GroupMembership
	queries.append(
		select(GroupMembership.user_id).where(
			GroupMembership.group_id.in_(
				select(AccessRule.subject_group_id).where(
					config.rule_fk == resource_id,
					AccessRule.subject_group_id.is_not(None),
					AccessRule.level.in_(allowed_levels),
				)
			)
		)
	)

	# 5. role access rules → expand via user_role_association
	queries.append(
		select(user_role_association.c.user_id).where(
			user_role_association.c.role_id.in_(
				select(AccessRule.subject_role_id).where(
					config.rule_fk == resource_id,
					AccessRule.subject_role_id.is_not(None),
					AccessRule.level.in_(allowed_levels),
				)
			)
		)
	)

	# 6. role resource defaults - roles whose default_permissions
	#    grant sufficient access for this resource type
	role_result = await session.execute(select(Role))
	default_role_ids = [
		r.id
		for r in role_result.scalars().all()
		if _role_grants_default(r, resource_type, required_level)
	]
	if default_role_ids:
		queries.append(
			select(user_role_association.c.user_id).where(
				user_role_association.c.role_id.in_(default_role_ids)
			)
		)

	# 7. global defaults - if the server-wide settings grant access,
	#    every active user qualifies
	global_level = settings.default_permissions.resource_access.get(resource_type)
	if global_level is not None and _level_satisfies(global_level, required_level):
		queries.append(select(User.id).where(User.is_active.is_(True)))

	if not queries:
		return []

	combined = union(*queries).subquery()
	result = await session.execute(select(combined.c[0]))
	return [TypeID(row[0]) for row in result.all()]


def _role_grants_default(
	role: Role,
	resource_type: ResourceType,
	required_level: AccessLevel,
) -> bool:
	"""check whether a role's default_permissions grant sufficient access."""
	level = role.get_default_permissions().resource_access.get(resource_type)
	return level is not None and _level_satisfies(level, required_level)


# resource-specific convenience wrappers
def thread_access_predicate(
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> ColumnElement[bool]:
	"""return a SQL predicate limiting threads to those accessible to principal."""
	return resource_access_predicate(
		principal,
		ResourceType.THREAD,
		required_level=required_level,
		include_deleted=include_hidden,
	)


def project_access_predicate(
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
) -> ColumnElement[bool]:
	"""return a SQL predicate limiting projects to those accessible to principal."""
	return resource_access_predicate(
		principal,
		ResourceType.PROJECT,
		required_level=required_level,
	)


async def get_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	owner_id: TypeID | None = None,
) -> AccessLevel | None:
	"""
	compute the effective access level for a principal on a specific resource.

	returns the effective access level, or None if no access is granted.

	evaluation order:
	1. superuser → admin
	2. owner → admin
	3. explicit resource rules (last match by order_index wins)
	4. merged defaults fallback (role + global defaults, highest-wins)
	"""
	if principal.is_admin:
		return AccessLevel.ADMIN

	if owner_id is not None and principal.user.id == owner_id:
		return AccessLevel.ADMIN

	config = RESOURCE_CONFIG[resource_type]

	# fetch explicit resource rules only
	stmt = (
		select(AccessRule)
		.where(config.rule_fk == resource_id)
		.order_by(AccessRule.order_index)
	)

	result = await session.execute(stmt)
	rules = list(result.scalars().all())

	return resolve_effective_level(principal, resource_type, rules)


def resolve_effective_level(
	principal: Principal,
	resource_type: ResourceType,
	rules: list[AccessRule],
	owner_id: TypeID | None = None,
) -> AccessLevel | None:
	"""compute effective level from already-fetched rules (pure, no DB).

	same evaluation order as ``get_effective_access_level`` but operates on
	a pre-loaded rules list so it can reuse a query that was already issued.
	"""
	if principal.is_admin:
		return AccessLevel.ADMIN

	if owner_id is not None and principal.user.id == owner_id:
		return AccessLevel.ADMIN

	effective_level: AccessLevel | None = None

	for rule in rules:
		applies = False
		if rule.subject_user_id is not None:
			applies = rule.subject_user_id == principal.user.id
		elif rule.subject_group_id is not None:
			applies = rule.subject_group_id in principal.group_ids
		elif rule.subject_role_id is not None:
			applies = rule.subject_role_id in principal.role_ids
		else:
			# public rule
			applies = True

		if applies:
			effective_level = rule.level

	# if no explicit rule matched, fall back to merged defaults
	if effective_level is None:
		effective_level = principal.role_resource_defaults.get(resource_type)

	return effective_level


async def require_resource_access(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
	include_deleted: bool = False,
	owner_id: TypeID | None = None,
) -> None:
	"""
	check that principal has required access level on a resource.

	raises 404 if resource doesn't exist or user doesn't have access.
	raises 403 if user explicitly denied or insufficient permission.
	"""
	config = RESOURCE_CONFIG[resource_type]

	# check resource existence and get owner_id if not provided
	stmt = select(config.id_col)
	if config.owner_fk is not None:
		stmt = select(config.id_col, config.owner_fk)

	if include_deleted and principal.is_admin:
		stmt = stmt.execution_options(include_deleted=True)

	stmt = stmt.where(config.id_col == resource_id)

	result = await session.execute(stmt)
	row = result.one_or_none()

	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	if config.owner_fk is not None and owner_id is None:
		owner_id = row[1] if len(row) > 1 else None

	effective = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		owner_id=owner_id,
	)

	if effective is None or not _level_satisfies(effective, required_level):
		# 404 to avoid leaking resource existence
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)


# resource-specific require helpers
async def require_thread_access(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> None:
	"""check that principal has required access level on a thread."""
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	await require_resource_access(
		thread_id,
		session,
		principal,
		ResourceType.THREAD,
		required_level=required_level,
		include_deleted=include_hidden,
	)


async def require_project_access(
	project_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
) -> None:
	"""check that principal has required access level on a project."""
	await require_resource_access(
		project_id,
		session,
		principal,
		ResourceType.PROJECT,
		required_level=required_level,
	)


def require_permission(principal: Principal, permission: str) -> None:
	"""check that principal has a global permission string."""
	if not principal.has_permission(permission):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def require_admin(principal: Principal) -> None:
	"""raise 403 if the principal is not an admin."""
	if not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="admin access required",
		)
