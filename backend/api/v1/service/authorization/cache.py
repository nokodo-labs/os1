"""accessible-user cache and recipient expansion for ACL resources."""

from __future__ import annotations

import asyncio
from typing import Literal

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.models.access_rule import AccessLevel, AccessRule
from api.models.group import GroupMembership
from api.models.many_to_many import user_role_association
from api.models.role import Role
from api.models.user import User
from api.permissions import ResourceType
from api.redis import cache
from api.settings import settings
from api.v1.service.authorization.config import (
	RESOURCE_CONFIG,
	allowed_levels,
	default_access_resource_types,
	level_satisfies,
	unique_resource_types,
)
from api.v1.service.authorization.inheritance import (
	load_descendant_resource_ids,
	load_parent_resource_refs,
)
from nokodo_ai.utils.typeid import TypeID


def accessible_users_tag(resource_type: ResourceType, resource_id: TypeID) -> str:
	return f"resource:{resource_type.value}:{resource_id}"


async def list_accessible_user_ids(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
) -> list[TypeID]:
	"""return all user IDs that have at least required_level access."""
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
		ttl=settings.cache.accessible_users_ttl_seconds,
		tags=[accessible_users_tag(resource_type, resource_id)],
	)
	return result


async def invalidate_accessible_users_for_resource(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession | None = None,
) -> None:
	"""invalidate accessible_users entries for a resource and descendants."""
	if session is None:
		await cache.invalidate_tag(accessible_users_tag(resource_type, resource_id))
		return
	tags = await _accessible_users_tags_for_acl_update(
		resource_type, resource_id, session
	)
	if tags:
		await asyncio.gather(*(cache.invalidate_tag(tag) for tag in tags))


async def _accessible_users_tags_for_acl_update(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
) -> set[str]:
	"""return cache tags for a resource and resources inheriting from it."""
	tags = {accessible_users_tag(resource_type, resource_id)}
	descendants = await load_descendant_resource_ids(
		resource_type, resource_id, session
	)
	for descendant_type, descendant_ids in descendants.items():
		for descendant_id in descendant_ids:
			tags.add(accessible_users_tag(descendant_type, descendant_id))
	return tags


async def invalidate_accessible_users_for_subject(
	subject_kind: Literal["user", "group", "role"],
	subject_id: TypeID,
	session: AsyncSession,
) -> None:
	"""invalidate accessible_users for every resource referencing a subject."""
	subject_col = {
		"user": AccessRule.subject_user_id,
		"group": AccessRule.subject_group_id,
		"role": AccessRule.subject_role_id,
	}[subject_kind]
	fk_cols = [(cfg.rule_fk, rtype) for rtype, cfg in RESOURCE_CONFIG.items()]
	stmt = select(*[col for col, _ in fk_cols]).where(subject_col == str(subject_id))
	rows = (await session.execute(stmt)).all()
	tags: set[str] = set()
	for row in rows:
		for value, (_col, resource_type) in zip(row, fk_cols, strict=True):
			if value is not None:
				tags.update(
					await _accessible_users_tags_for_acl_update(
						resource_type,
						TypeID(str(value)),
						session,
					)
				)
	if tags:
		await asyncio.gather(*(cache.invalidate_tag(tag) for tag in tags))


async def invalidate_accessible_users_for_resource_types(
	resource_types: list[ResourceType],
	session: AsyncSession,
) -> None:
	"""invalidate accessible_users entries for every resource of each type."""
	tags: set[str] = set()
	for resource_type in unique_resource_types(resource_types):
		config = RESOURCE_CONFIG[resource_type]
		rows = (await session.execute(select(config.id_col))).all()
		for row in rows:
			tags.update(
				await _accessible_users_tags_for_acl_update(
					resource_type,
					TypeID(str(row[0])),
					session,
				)
			)
	if tags:
		await asyncio.gather(*(cache.invalidate_tag(tag) for tag in tags))


async def invalidate_accessible_users_for_role_defaults(
	role_ids: list[TypeID],
	session: AsyncSession,
) -> None:
	"""invalidate default-access resource caches affected by role membership."""
	if not role_ids:
		return
	roles = (
		(await session.execute(select(Role).where(Role.id.in_(role_ids))))
		.scalars()
		.all()
	)
	resource_types: list[ResourceType] = []
	for role in roles:
		resource_types.extend(
			default_access_resource_types(
				role.get_default_permissions().resource_access
			)
		)
	await invalidate_accessible_users_for_resource_types(resource_types, session)


async def _list_accessible_user_ids_uncached(
	resource_type: ResourceType,
	resource_id: TypeID,
	session: AsyncSession,
	required_level: AccessLevel = AccessLevel.READER,
	visited_resource_refs: set[tuple[ResourceType, TypeID]] | None = None,
) -> list[TypeID]:
	if visited_resource_refs is None:
		visited_resource_refs = set()
	resource_ref = (resource_type, resource_id)
	if resource_ref in visited_resource_refs:
		return []
	visited_resource_refs.add(resource_ref)

	config = RESOURCE_CONFIG[resource_type]
	matching_levels = allowed_levels(required_level)
	queries: list[Select] = []

	if config.owner_fk is not None:
		queries.append(select(config.owner_fk).where(config.id_col == resource_id))

	queries.append(select(User.id).where(User.is_superuser.is_(True)))

	queries.append(
		select(AccessRule.subject_user_id).where(
			config.rule_fk == resource_id,
			AccessRule.subject_user_id.is_not(None),
			AccessRule.level.in_(matching_levels),
		)
	)

	queries.append(
		select(GroupMembership.user_id).where(
			GroupMembership.group_id.in_(
				select(AccessRule.subject_group_id).where(
					config.rule_fk == resource_id,
					AccessRule.subject_group_id.is_not(None),
					AccessRule.level.in_(matching_levels),
				)
			)
		)
	)

	queries.append(
		select(user_role_association.c.user_id).where(
			user_role_association.c.role_id.in_(
				select(AccessRule.subject_role_id).where(
					config.rule_fk == resource_id,
					AccessRule.subject_role_id.is_not(None),
					AccessRule.level.in_(matching_levels),
				)
			)
		)
	)

	role_result = await session.execute(select(Role))
	default_role_ids = [
		role.id
		for role in role_result.scalars().all()
		if _role_grants_default(role, resource_type, required_level)
	]
	if default_role_ids:
		queries.append(
			select(user_role_association.c.user_id).where(
				user_role_association.c.role_id.in_(default_role_ids)
			)
		)

	global_level = settings.default_permissions.resource_access.get(resource_type)
	if global_level is not None and level_satisfies(global_level, required_level):
		queries.append(select(User.id).where(User.is_active.is_(True)))

	if not queries:
		return []

	combined = union(*queries).subquery()
	result = await session.execute(select(combined.c[0]))
	user_ids = {TypeID(row[0]) for row in result.all()}
	for parent_type, parent_id in await load_parent_resource_refs(
		resource_type, resource_id, session
	):
		user_ids.update(
			await _list_accessible_user_ids_uncached(
				parent_type,
				parent_id,
				session,
				required_level=required_level,
				visited_resource_refs=visited_resource_refs,
			)
		)
	return list(user_ids)


def _role_grants_default(
	role: Role,
	resource_type: ResourceType,
	required_level: AccessLevel,
) -> bool:
	level = role.get_default_permissions().resource_access.get(resource_type)
	return level is not None and level_satisfies(level, required_level)
