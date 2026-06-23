"""effective access resolution and require helpers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.permissions import ResourceType, higher_access, highest_access
from api.v1.service.auth import Principal
from api.v1.service.authorization.config import RESOURCE_CONFIG, level_satisfies
from api.v1.service.authorization.inheritance import load_parent_resource_refs
from nokodo_ai.utils.typeid import TypeID


async def get_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	owner_id: TypeID | None = None,
	visited_resource_refs: set[tuple[ResourceType, TypeID]] | None = None,
) -> AccessLevel | None:
	"""compute the effective access level for a principal on a resource."""
	if principal.is_admin:
		return AccessLevel.ADMIN
	if visited_resource_refs is None:
		visited_resource_refs = set()
	resource_ref = (resource_type, resource_id)
	if resource_ref in visited_resource_refs:
		return None
	visited_resource_refs.add(resource_ref)

	config = RESOURCE_CONFIG[resource_type]
	if owner_id is None:
		owner_stmt = select(config.id_col)
		if config.owner_fk is not None:
			owner_stmt = select(config.id_col, config.owner_fk)
		owner_stmt = owner_stmt.where(config.id_col == resource_id)
		owner_row = (await session.execute(owner_stmt)).one_or_none()
		if owner_row is None:
			return None
		if config.owner_fk is not None and len(owner_row) > 1:
			owner_id = owner_row[1]

	if owner_id is not None and principal.user.id == owner_id:
		return AccessLevel.ADMIN

	stmt = (
		select(AccessRule)
		.where(config.rule_fk == resource_id)
		.order_by(AccessRule.order_index)
	)
	result = await session.execute(stmt)
	rules = list(result.scalars().all())

	direct_level = resolve_effective_level(principal, resource_type, rules)
	inherited_level = await _get_inherited_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		visited_resource_refs,
	)
	return higher_access(direct_level, inherited_level)


async def _get_inherited_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	visited_resource_refs: set[tuple[ResourceType, TypeID]],
) -> AccessLevel | None:
	parent_levels: list[AccessLevel | None] = []
	for parent_type, parent_id in await load_parent_resource_refs(
		resource_type, resource_id, session
	):
		parent_levels.append(
			await get_effective_access_level(
				session,
				principal,
				parent_type,
				parent_id,
				visited_resource_refs=visited_resource_refs,
			)
		)
	return highest_access(parent_levels)


def resolve_effective_level(
	principal: Principal,
	resource_type: ResourceType,
	rules: list[AccessRule],
	owner_id: TypeID | None = None,
) -> AccessLevel | None:
	"""compute direct effective level from already-fetched rules."""
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
			applies = True

		if applies:
			effective_level = rule.level

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
	"""check that principal has required access level on a resource."""
	config = RESOURCE_CONFIG[resource_type]

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
	if effective is None or not level_satisfies(effective, required_level):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)


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
