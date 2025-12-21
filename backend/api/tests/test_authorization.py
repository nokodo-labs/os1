"""Tests for authorization helpers."""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy import true
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.acl import AccessRole
from api.models.user import User
from api.v1.service import authorization
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_require_thread_and_project_access(db_session: AsyncSession) -> None:
	user = User(email="authz@example.com", hashed_password="pw", is_active=True)
	db_session.add(user)
	await db_session.commit()
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	with pytest.raises(HTTPException):
		await authorization.require_thread_access(
			new_typeid("thread"), db_session, principal=principal
		)

	with pytest.raises(HTTPException):
		await authorization.require_project_access(
			new_typeid("proj"), db_session, principal=principal
		)


def test_require_permission_denied() -> None:
	user = User(email="authz-deny@example.com", hashed_password="pw", is_active=True)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		authorization.require_permission(principal, "agents:manage")


def test_allowed_roles_default_case() -> None:
	assert authorization._allowed_roles(cast(AccessRole, "unexpected")) == (
		AccessRole.ADMIN,
	)


@pytest.mark.asyncio
async def test_authorization_admin_predicates(db_session: AsyncSession) -> None:
	admin = User(
		email="authz-admin@example.com",
		hashed_password="pw",
		is_active=True,
		is_superuser=True,
	)
	db_session.add(admin)
	await db_session.commit()
	principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	assert authorization._allowed_roles(AccessRole.ADMIN) == (AccessRole.ADMIN,)
	assert authorization.thread_access_predicate(principal).compare(true())
	assert authorization.project_access_predicate(principal).compare(true())
