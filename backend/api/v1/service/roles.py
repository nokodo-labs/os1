"""service helpers for role operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.many_to_many import user_role_association
from api.models.role import Role
from api.models.user import User
from api.permissions import DefaultPermissions
from api.schemas.role import RoleCreate, RoleUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.sorting import SortDir, apply_sort


async def list_roles(
	session: AsyncSession,
	*,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	sort_by: str = "priority",
	sort_dir: SortDir = "desc",
	user_id: str | None = None,
) -> list[Role]:
	"""list all roles (requires roles:read permission)."""
	require_permission(principal, "roles:read")
	stmt = select(Role)
	if user_id is not None:
		stmt = stmt.join(
			user_role_association,
			user_role_association.c.role_id == Role.id,
		).where(user_role_association.c.user_id == user_id)
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


async def get_role(
	role_id: str,
	session: AsyncSession,
	*,
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
	*,
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
	role_id: str,
	role_in: RoleUpdate,
	session: AsyncSession,
	*,
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
	update_data = role_in.model_dump(exclude_unset=True)
	for field, value in update_data.items():
		if field == "metadata":
			role.metadata_ = value
		elif field == "default_permissions" and value is not None:
			dp = DefaultPermissions.model_validate(value)
			role.default_permissions = dp.model_dump(
				mode="json",
				exclude_none=True,
			)
		else:
			setattr(role, field, value)
	await session.commit()
	await session.refresh(role)
	return role


async def delete_role(
	role_id: str,
	session: AsyncSession,
	*,
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
	await session.delete(role)
	await session.commit()


# role members


async def list_role_members(
	role_id: str,
	session: AsyncSession,
	*,
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
	role_id: str,
	user_ids: list[str],
	session: AsyncSession,
	*,
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
	await session.commit()
	# return updated member list
	return await list_role_members(
		role_id, session, principal=principal, skip=0, limit=200
	)
