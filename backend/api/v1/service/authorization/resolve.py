"""effective access resolution and require helpers."""

from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.permissions import (
	PermissionGrant,
	ResourceType,
	higher_access,
	highest_access,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization.config import (
	MAX_INHERITANCE_DEPTH,
	RESOURCE_CONFIG,
	inherited_child_level,
	is_acl_resource_config,
	level_satisfies,
)
from api.v1.service.authorization.inheritance import (
	ParentResourceRef,
	load_parent_resource_refs,
)
from api.v1.service.authorization.predicates import resource_access_predicate
from nokodo_ai.types.sentinels import MISSING, MissingType
from nokodo_ai.utils.typeid import TypeID


type _ResolutionKey = tuple[ResourceType, TypeID, bool, int]
type _ResourceKey = tuple[ResourceType, TypeID]


@dataclass(slots=True)
class AccessGraphCache:
	"""principal-independent access graph facts reused within one request."""

	owners: dict[_ResourceKey, TypeID | None | MissingType] = field(
		default_factory=dict
	)
	missing_resources: set[_ResourceKey] = field(default_factory=set)
	rules: dict[_ResourceKey, list[AccessRule]] = field(default_factory=dict)
	parents: dict[_ResourceKey, list[ParentResourceRef]] = field(default_factory=dict)
	authors: dict[_ResourceKey, TypeID | None] = field(default_factory=dict)


async def get_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	owner_id: TypeID | None | MissingType = MISSING,
	rules: list[AccessRule] | None = None,
	resolved_levels: dict[_ResolutionKey, AccessLevel | None] | None = None,
	resolving_resource_refs: set[_ResolutionKey] | None = None,
	non_transitive_used: bool = False,
	include_link_access: bool = False,
	traversal_depth: int = 0,
	graph_cache: AccessGraphCache | None = None,
) -> AccessLevel | None:
	"""compute the effective access level for a principal on a resource."""
	if principal.is_resource_operator(resource_type):
		return AccessLevel.ADMIN
	if resolved_levels is None:
		resolved_levels = {}
	if resolving_resource_refs is None:
		resolving_resource_refs = set()
	if graph_cache is None:
		graph_cache = AccessGraphCache()
	resource_ref = (
		resource_type,
		resource_id,
		non_transitive_used,
		traversal_depth,
	)
	if resource_ref in resolved_levels:
		return resolved_levels[resource_ref]
	if resource_ref in resolving_resource_refs:
		return None
	resolving_resource_refs.add(resource_ref)
	try:
		level = await _resolve_effective_access_level(
			session,
			principal,
			resource_type,
			resource_id,
			owner_id,
			rules,
			resolved_levels,
			resolving_resource_refs,
			non_transitive_used,
			include_link_access,
			traversal_depth,
			graph_cache,
		)
	finally:
		resolving_resource_refs.remove(resource_ref)
	resolved_levels[resource_ref] = level
	return level


async def _resolve_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	owner_id: TypeID | None | MissingType,
	rules: list[AccessRule] | None,
	resolved_levels: dict[_ResolutionKey, AccessLevel | None],
	resolving_resource_refs: set[_ResolutionKey],
	non_transitive_used: bool,
	include_link_access: bool,
	traversal_depth: int,
	graph_cache: AccessGraphCache,
) -> AccessLevel | None:
	"""resolve one uncached resource within an access graph walk."""

	config = RESOURCE_CONFIG[resource_type]
	if not is_acl_resource_config(config):
		# leaves hold no rules: every level they can reach comes through a link.
		return await _get_inherited_effective_access_level(
			session,
			principal,
			resource_type,
			resource_id,
			resolved_levels,
			resolving_resource_refs,
			non_transitive_used,
			include_link_access,
			traversal_depth,
			graph_cache,
		)
	if owner_id is MISSING:
		resource_key = (resource_type, resource_id)
		if resource_key in graph_cache.missing_resources:
			return None
		if resource_key not in graph_cache.owners:
			owner_stmt = select(config.id_col)
			if config.owner_fk is not None:
				owner_stmt = select(config.id_col, config.owner_fk)
			owner_stmt = owner_stmt.where(config.id_col == resource_id)
			owner_row = (await session.execute(owner_stmt)).one_or_none()
			if owner_row is None:
				graph_cache.missing_resources.add(resource_key)
				return None
			graph_cache.owners[resource_key] = (
				owner_row[1] if config.owner_fk is not None else MISSING
			)
		owner_id = graph_cache.owners[resource_key]

	if owner_id is not MISSING and owner_id is not None:
		if principal.user.id == owner_id:
			return AccessLevel.ADMIN

	if rules is None:
		resource_key = (resource_type, resource_id)
		if resource_key not in graph_cache.rules:
			stmt = (
				select(AccessRule)
				.where(config.rule_fk == resource_id)
				.order_by(AccessRule.order_index, AccessRule.id)
			)
			result = await session.execute(stmt)
			graph_cache.rules[resource_key] = list(result.scalars().all())
		rules = graph_cache.rules[resource_key]

	direct_level = resolve_effective_level(
		principal,
		resource_type,
		rules,
		owner_id=owner_id,
		include_link_access=include_link_access,
	)
	if direct_level == AccessLevel.ADMIN:
		return direct_level
	inherited_level = await _get_inherited_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		resolved_levels,
		resolving_resource_refs,
		non_transitive_used,
		include_link_access,
		traversal_depth,
		graph_cache,
	)
	return higher_access(direct_level, inherited_level)


async def _get_inherited_effective_access_level(
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	resource_id: TypeID,
	resolved_levels: dict[_ResolutionKey, AccessLevel | None],
	resolving_resource_refs: set[_ResolutionKey],
	non_transitive_used: bool,
	include_link_access: bool,
	traversal_depth: int,
	graph_cache: AccessGraphCache,
) -> AccessLevel | None:
	if traversal_depth >= MAX_INHERITANCE_DEPTH:
		return None
	parent_levels: list[AccessLevel | None] = []
	is_author = await _is_author(
		session, resource_type, resource_id, principal, graph_cache
	)
	resource_key = (resource_type, resource_id)
	if resource_key not in graph_cache.parents:
		graph_cache.parents[resource_key] = await load_parent_resource_refs(
			resource_type, resource_id, session
		)
	for ref in graph_cache.parents[resource_key]:
		if not ref.transitive and non_transitive_used:
			continue
		parent_level = await get_effective_access_level(
			session,
			principal,
			ref.parent_type,
			ref.parent_id,
			resolved_levels=resolved_levels,
			resolving_resource_refs=resolving_resource_refs,
			non_transitive_used=non_transitive_used or not ref.transitive,
			include_link_access=include_link_access,
			traversal_depth=traversal_depth + 1,
			graph_cache=graph_cache,
		)
		if parent_level is None:
			continue
		parent_levels.append(
			inherited_child_level(ref.inherited_levels, parent_level, is_author)
		)
	return highest_access(parent_levels)


async def _is_author(
	session: AsyncSession,
	resource_type: ResourceType,
	resource_id: TypeID,
	principal: Principal,
	graph_cache: AccessGraphCache,
) -> bool:
	"""whether the principal authored the row, for author-gated inheritance."""
	config = RESOURCE_CONFIG[resource_type]
	if config.author_fk is None:
		return False
	resource_key = (resource_type, resource_id)
	if resource_key not in graph_cache.authors:
		graph_cache.authors[resource_key] = await session.scalar(
			select(config.author_fk).where(config.id_col == resource_id)
		)
	author_id = graph_cache.authors[resource_key]
	return author_id is not None and author_id == principal.user.id


def resolve_effective_level(
	principal: Principal,
	resource_type: ResourceType,
	rules: list[AccessRule],
	owner_id: TypeID | None | MissingType = MISSING,
	include_link_access: bool = False,
) -> AccessLevel | None:
	"""compute direct effective level from already-fetched rules."""
	if principal.is_resource_operator(resource_type):
		return AccessLevel.ADMIN

	if owner_id is not MISSING and owner_id is not None:
		if principal.user.id == owner_id:
			return AccessLevel.ADMIN

	effective_level = (
		principal.role_resource_defaults.get(resource_type)
		if owner_id is not MISSING and owner_id is not None
		else None
	)
	for rule in rules:
		granted_level: AccessLevel | None = None
		if rule.subject_user_id is not None:
			if rule.subject_user_id == principal.user.id:
				granted_level = rule.level
		elif rule.subject_group_id is not None:
			if rule.subject_group_id in principal.group_ids:
				granted_level = rule.level
		elif rule.subject_role_id is not None:
			if rule.subject_role_id in principal.role_ids:
				granted_level = rule.level
		elif include_link_access:
			granted_level = AccessLevel.READER

		effective_level = higher_access(effective_level, granted_level)

	return effective_level


async def require_resource_access(
	resource_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	resource_type: ResourceType,
	required_level: AccessLevel = AccessLevel.READER,
	include_deleted: bool = False,
	include_hidden: bool = False,
	owner_id: TypeID | None | MissingType = MISSING,
) -> None:
	"""check that principal has required access level on a resource."""
	if (include_deleted or include_hidden) and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	config = RESOURCE_CONFIG[resource_type]
	if not is_acl_resource_config(config):
		stmt = select(config.id_col).where(
			config.id_col == resource_id,
			resource_access_predicate(
				principal,
				resource_type,
				required_level=required_level,
				include_link_access=True,
			),
		)
		if config.hidden_col is not None and not include_hidden:
			stmt = stmt.where(config.hidden_col.is_(False))
		if include_deleted:
			stmt = stmt.execution_options(include_deleted=True)
		if (await session.scalar(stmt)) is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"{resource_type.value} not found",
			)
		return

	stmt = select(config.id_col)
	if config.owner_fk is not None:
		stmt = select(config.id_col, config.owner_fk)

	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)

	stmt = stmt.where(config.id_col == resource_id)
	if config.hidden_col is not None and not include_hidden:
		stmt = stmt.where(config.hidden_col.is_(False))
	result = await session.execute(stmt)
	row = result.one_or_none()

	if row is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"{resource_type.value} not found",
		)

	if owner_id is MISSING:
		owner_id = row[1] if config.owner_fk is not None else None

	effective = await get_effective_access_level(
		session,
		principal,
		resource_type,
		resource_id,
		owner_id=owner_id,
		include_link_access=True,
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
	include_deleted: bool = False,
) -> None:
	"""check that principal has required access level on a thread."""
	await require_resource_access(
		thread_id,
		session,
		principal,
		ResourceType.THREAD,
		required_level,
		include_deleted=include_deleted,
		include_hidden=include_hidden,
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


def require_permission(
	principal: Principal,
	permission: PermissionGrant,
) -> None:
	"""check that principal holds one action permission."""
	if not principal.has_permission(permission):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def require_admin(principal: Principal) -> None:
	"""raise 403 if the principal is not an admin."""
	if not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="admin access required",
		)


def require_self_or_permission(
	subject_user_id: TypeID,
	principal: Principal,
	permission: PermissionGrant,
) -> None:
	"""raise 403 unless the subject is the caller or the caller holds permission."""
	if subject_user_id == principal.user.id:
		return
	require_permission(principal, permission)
