"""service helpers for role operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.permissions import DefaultPermissions
from api.models.role import Role
from api.schemas.role import RoleCreate, RoleUpdate
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission


async def list_roles(
	session: AsyncSession,
	*,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
) -> list[Role]:
	"""list all roles (requires roles:read permission)."""
	require_permission(principal, "roles:read")
	stmt = select(Role).offset(skip).limit(limit).order_by(Role.priority.desc())
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
	"""create a new role (requires roles:admin permission)."""
	require_permission(principal, "roles:admin")
	role = Role(
		name=role_in.name,
		description=role_in.description,
		default_permissions=role_in.default_permissions.model_dump(mode="json"),
		quotas=role_in.quotas,
		priority=role_in.priority,
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
	"""update an existing role (requires roles:admin permission)."""
	require_permission(principal, "roles:admin")
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
			role.default_permissions = dp.model_dump(mode="json")
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
	"""delete a role (requires roles:admin permission)."""
	require_permission(principal, "roles:admin")
	role = await session.get(Role, role_id)
	if role is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="role not found",
		)
	await session.delete(role)
	await session.commit()
