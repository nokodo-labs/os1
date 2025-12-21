"""Authorization helpers for the API service layer."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import exists, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from api.models.acl import AccessControlEntry, AccessRole
from api.models.project import Project
from api.models.thread import Thread
from api.v1.service.auth import Principal


def _allowed_roles(required: AccessRole) -> tuple[AccessRole, ...]:
	match required:
		case AccessRole.VIEWER:
			return (AccessRole.VIEWER, AccessRole.EDITOR, AccessRole.ADMIN)
		case AccessRole.EDITOR:
			return (AccessRole.EDITOR, AccessRole.ADMIN)
		case AccessRole.ADMIN:
			return (AccessRole.ADMIN,)
		case _:
			return (AccessRole.ADMIN,)


def thread_access_predicate(
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
) -> ColumnElement[bool]:
	"""Return a SQL predicate limiting threads to those accessible to principal."""
	if principal.is_admin:
		return true()

	allowed_roles = _allowed_roles(required_role)
	user_id = principal.user.id

	user_acl = exists(
		select(1).where(
			AccessControlEntry.thread_id == Thread.id,
			AccessControlEntry.user_id == user_id,
			AccessControlEntry.role.in_(allowed_roles),
		)
	)
	group_acl = exists(
		select(1).where(
			AccessControlEntry.thread_id == Thread.id,
			AccessControlEntry.group_id.in_(principal.group_ids),
			AccessControlEntry.role.in_(allowed_roles),
		)
	)

	return or_(Thread.owner_id == user_id, user_acl, group_acl)


def project_access_predicate(
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
) -> ColumnElement[bool]:
	"""Return a SQL predicate limiting projects to those accessible to principal."""
	if principal.is_admin:
		return true()

	allowed_roles = _allowed_roles(required_role)
	user_id = principal.user.id

	user_acl = exists(
		select(1).where(
			AccessControlEntry.project_id == Project.id,
			AccessControlEntry.user_id == user_id,
			AccessControlEntry.role.in_(allowed_roles),
		)
	)
	group_acl = exists(
		select(1).where(
			AccessControlEntry.project_id == Project.id,
			AccessControlEntry.group_id.in_(principal.group_ids),
			AccessControlEntry.role.in_(allowed_roles),
		)
	)

	return or_(Project.owner_id == user_id, user_acl, group_acl)


async def require_thread_access(
	thread_id: str,
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
) -> None:
	stmt = (
		select(Thread.id)
		.where(Thread.id == thread_id)
		.where(thread_access_predicate(principal, required_role=required_role))
	)
	if (await session.execute(stmt)).scalar_one_or_none() is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)


async def require_project_access(
	project_id: str,
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
) -> None:
	stmt = (
		select(Project.id)
		.where(Project.id == project_id)
		.where(project_access_predicate(principal, required_role=required_role))
	)
	if (await session.execute(stmt)).scalar_one_or_none() is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Project not found",
		)


def require_permission(principal: Principal, permission: str) -> None:
	if not principal.has_permission(permission):
		raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
