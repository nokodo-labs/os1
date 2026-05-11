"""service helpers for role operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.many_to_many import user_role_association
from api.models.role import ROLE_TYPEID_PREFIX, Role
from api.models.user import User
from api.permissions import (
	DEFAULT_ACCESS_RESOURCE_TYPES,
	DefaultPermissions,
	ResourceType,
)
from api.schemas.role import RoleCreate, RoleListFilters, RoleUpdate
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	changed_default_access_resource_types,
	invalidate_accessible_users_for_resource_types,
	invalidate_accessible_users_for_subject,
	require_permission,
)
from api.v1.service.listing import SortDir, apply_sort, exact_typeid_filter
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


async def _role_member_ids(role_id: TypeID, session: AsyncSession) -> list[TypeID]:
	"""return all user IDs assigned to a role."""
	result = await session.execute(
		select(user_role_association.c.user_id).where(
			user_role_association.c.role_id == role_id,
		)
	)
	# association columns are plain strings; normalize at the service boundary.
	return [TypeID(str(uid)) for uid in result.scalars().all()]


async def _notify_role_members(
	role_id: TypeID,
	member_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	event_type: EventType = EventType.ROLE_UPDATED,
) -> None:
	if not member_ids:
		return
	event = Event(
		scope=EventScope.SYSTEM,
		type=event_type,
		data={"role_id": role_id},
		user_id=principal.user_id,
	)
	await event_service.publish_event(
		session,
		event=event,
		recipient_ids=member_ids,
	)


def _role_default_resource_types(role: Role) -> list[ResourceType]:
	"""return resource types touched by a role's default access."""
	defaults = role.get_default_permissions().resource_access
	return [
		resource_type
		for resource_type in DEFAULT_ACCESS_RESOURCE_TYPES
		if defaults.get(resource_type) is not None
	]


def _apply_role_filters(stmt: Select, role_filters: RoleListFilters) -> Select:
	"""apply role list/count filters."""
	if role_filters.user_id is not None:
		stmt = stmt.join(
			user_role_association,
			user_role_association.c.role_id == Role.id,
		).where(user_role_association.c.user_id == role_filters.user_id)
	if role_filters.q and role_filters.q.strip():
		pattern = contains_pattern(role_filters.q.strip())
		stmt = stmt.where(
			or_(
				Role.name.ilike(pattern, escape="\\"),
				Role.description.ilike(pattern, escape="\\"),
				exact_typeid_filter(Role.id, role_filters.q, ROLE_TYPEID_PREFIX),
			)
		)
	return stmt


async def list_roles(
	session: AsyncSession,
	principal: Principal,
	filters: RoleListFilters | None = None,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "priority",
	sort_dir: SortDir = "desc",
) -> list[Role]:
	"""list all roles (requires roles:read permission)."""
	require_permission(principal, "roles:read")
	role_filters = filters or RoleListFilters()
	stmt = _apply_role_filters(select(Role), role_filters)
	stmt = (
		apply_sort(
			stmt,
			sort_by=sort_by,
			sort_dir=sort_dir,
			columns={
				"priority": Role.priority,
				"name": Role.name,
				"created_at": Role.created_at,
				"updated_at": Role.updated_at,
			},
			tie_breaker=Role.id,
		)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def count_roles(
	session: AsyncSession,
	principal: Principal,
	filters: RoleListFilters | None = None,
) -> int:
	"""count roles matching the list filters."""
	require_permission(principal, "roles:read")
	role_filters = filters or RoleListFilters()
	stmt = _apply_role_filters(select(func.count()).select_from(Role), role_filters)
	return await session.scalar(stmt) or 0


async def get_role(
	role_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> Role:
	"""get a single role by id (requires roles:read permission)."""
	require_permission(principal, "roles:read")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	return role


async def create_role(
	role_in: RoleCreate,
	session: AsyncSession,
	principal: Principal,
) -> Role:
	"""create a new role (requires roles:manage permission)."""
	require_permission(principal, "roles:manage")
	priority = role_in.priority
	if priority is None:
		max_priority = await session.scalar(select(func.max(Role.priority)))
		priority = 0 if max_priority is None else max_priority + 1
	role = Role(
		name=role_in.name,
		description=role_in.description,
		default_permissions=role_in.default_permissions.model_dump(
			mode="json",
			exclude_none=True,
		),
		quotas=role_in.quotas,
		priority=priority,
		metadata_=role_in.metadata,
	)
	session.add(role)
	await session.commit()
	await session.refresh(role)
	return role


async def update_role(
	role_id: TypeID,
	role_in: RoleUpdate,
	session: AsyncSession,
	principal: Principal,
) -> Role:
	"""update an existing role (requires roles:manage permission)."""
	require_permission(principal, "roles:manage")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	changed = role_in.model_fields_set
	member_ids = await _role_member_ids(role_id, session)
	changed_default_resource_types: list[ResourceType] = []
	update_data = role_in.model_dump(
		exclude_unset=True,
		by_alias=True,
		exclude={"default_permissions"},
	)
	default_permissions_changed = False
	for key, value in update_data.items():
		setattr(role, key, value)
	if "default_permissions" in changed:
		previous_default_permissions = role.get_default_permissions()
		default_permissions = role_in.default_permissions
		if not isinstance(default_permissions, DefaultPermissions):
			raise ValueError("invalid default permissions")
		role.set_default_permissions(default_permissions)
		changed_default_resource_types = changed_default_access_resource_types(
			previous_default_permissions.resource_access,
			default_permissions.resource_access,
		)
		default_permissions_changed = True
	await session.commit()
	await session.refresh(role)
	if default_permissions_changed:
		# role defaults changed.
		await invalidate_accessible_users_for_subject("role", role_id, session)
		await invalidate_accessible_users_for_resource_types(
			changed_default_resource_types, session
		)
		await _notify_role_members(role_id, member_ids, session, principal)
	# priority only affects role ordering in admin views. resource defaults merge by
	# highest access level, so priority-only updates do not change effective access.
	return role


async def delete_role(
	role_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete a role (requires roles:manage permission)."""
	require_permission(principal, "roles:manage")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	# resolve affected users before deletion
	member_ids = await _role_member_ids(role_id, session)
	changed_default_resource_types = changed_default_access_resource_types(
		role.get_default_permissions().resource_access,
		DefaultPermissions().resource_access,
	)
	await invalidate_accessible_users_for_subject("role", role_id, session)
	await invalidate_accessible_users_for_resource_types(
		changed_default_resource_types, session
	)
	await session.delete(role)
	await session.commit()

	await _notify_role_members(
		role_id,
		member_ids,
		session,
		principal,
		event_type=EventType.ROLE_DELETED,
	)


# role members


async def list_role_members(
	role_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
) -> list[User]:
	"""list users assigned to a role (requires roles:read)."""
	require_permission(principal, "roles:read")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	stmt = (
		select(User)
		.join(
			user_role_association,
			user_role_association.c.user_id == User.id,
		)
		.where(user_role_association.c.role_id == role_id)
		.order_by(User.email)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def set_role_members(
	role_id: TypeID,
	user_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
) -> list[User]:
	"""replace the entire member list for a role (requires roles:manage)."""
	require_permission(principal, "roles:manage")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	# capture old members before clearing
	old_member_ids = await _role_member_ids(role_id, session)
	# clear existing members
	await session.execute(
		delete(user_role_association).where(
			user_role_association.c.role_id == role_id,
		)
	)
	# insert new members
	if user_ids:
		await session.execute(
			insert(user_role_association),
			[{"role_id": role_id, "user_id": uid} for uid in user_ids],
		)
	default_resource_types = _role_default_resource_types(role)
	await session.commit()
	await invalidate_accessible_users_for_subject("role", role_id, session)
	await invalidate_accessible_users_for_resource_types(
		default_resource_types, session
	)

	# notify all affected users (old + new members) so frontends refresh
	all_affected = set(old_member_ids) | set(user_ids)
	await _notify_role_members(role_id, list(all_affected), session, principal)

	# return updated member list
	return await list_role_members(
		role_id, session, principal=principal, skip=0, limit=200
	)
