"""authorization helpers for the API service layer."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import and_, exists, literal, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.file import File
from api.models.group import Group
from api.models.memory import Memory
from api.models.note import Note
from api.models.plugin import Plugin
from api.models.project import Project
from api.models.prompt import Prompt
from api.models.task import Task
from api.models.thread import Thread
from api.permissions import ResourceType
from api.v1.service.auth import Principal


@dataclass(frozen=True, slots=True)
class ResourceConfig:
	"""config for a resource type's access control."""

	id_col: InstrumentedAttribute
	rule_fk: InstrumentedAttribute
	owner_fk: InstrumentedAttribute | None
	deleted_at_col: InstrumentedAttribute | None
	is_temporary_col: InstrumentedAttribute | None = None


# resource type → access control config
RESOURCE_CONFIG: dict[ResourceType, ResourceConfig] = {
	ResourceType.THREAD: ResourceConfig(
		id_col=Thread.id,
		rule_fk=AccessRule.thread_id,
		owner_fk=Thread.owner_id,
		deleted_at_col=Thread.deleted_at,
		is_temporary_col=Thread.is_temporary,
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
	*,
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
	if config.deleted_at_col is not None:
		visibility = (
			true()
			if include_deleted and principal.is_admin
			else config.deleted_at_col.is_(None)
		)
	else:
		visibility = true()

	# temporary threads
	if config.is_temporary_col is not None:
		if not (include_deleted and principal.is_admin):
			visibility = and_(visibility, config.is_temporary_col.is_(False))

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

	# check if the principal's role_resource_defaults grant sufficient access
	default_level = principal.role_resource_defaults.get(resource_type)
	has_default_access = default_level is not None and _level_satisfies(
		default_level, required_level
	)

	if owner_fk is not None:
		base_access = or_(
			owner_fk == user_id, user_rule, group_rule, role_rule, public_rule
		)
	else:
		base_access = or_(user_rule, group_rule, role_rule, public_rule)

	if has_default_access:
		base_access = or_(base_access, true())

	return and_(base_access, visibility)


# backwards-compatible aliases
def thread_access_predicate(
	principal: Principal,
	*,
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
	*,
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
	resource_id: str,
	*,
	owner_id: str | None = None,
) -> AccessLevel | None:
	"""
	compute the effective access level for a principal on a specific resource.

	returns the effective access level, or None if no access is granted.

	evaluation order:
	1. superuser → admin
	2. owner → admin
	3. explicit resource rules (last match by order_index wins)
	4. role_resource_defaults fallback (highest across all roles)
	"""
	if principal.is_admin:
		return AccessLevel.ADMIN

	if owner_id is not None and str(principal.user.id) == str(owner_id):
		return AccessLevel.ADMIN

	config = RESOURCE_CONFIG[resource_type]

	# fetch explicit resource rules only
	stmt = (
		select(AccessRule)
		.where(config.rule_fk == resource_id)
		.order_by(AccessRule.order_index)
	)

	result = await session.execute(stmt)
	rules = result.scalars().all()

	effective_level: AccessLevel | None = None

	for rule in rules:
		applies = False
		if rule.subject_user_id is not None:
			applies = str(rule.subject_user_id) == str(principal.user.id)
		elif rule.subject_group_id is not None:
			applies = str(rule.subject_group_id) in principal.group_ids
		elif rule.subject_role_id is not None:
			applies = str(rule.subject_role_id) in principal.role_ids
		else:
			# public rule
			applies = True

		if applies:
			effective_level = rule.level

	# if no explicit rule matched, fall back to role_resource_defaults
	if effective_level is None:
		effective_level = principal.role_resource_defaults.get(
			resource_type,
		)

	return effective_level


async def require_resource_access(
	resource_id: str,
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	*,
	required_level: AccessLevel = AccessLevel.READER,
	include_deleted: bool = False,
	owner_id: str | None = None,
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
		owner_id = str(row[1]) if len(row) > 1 else None

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


# backwards-compatible helpers
async def require_thread_access(
	thread_id: str,
	session: AsyncSession,
	principal: Principal,
	*,
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
	project_id: str,
	session: AsyncSession,
	principal: Principal,
	*,
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
