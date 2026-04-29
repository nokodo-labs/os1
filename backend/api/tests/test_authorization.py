"""Tests for authorization helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import true
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.thread import Thread
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.v1.service import authorization
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.mark.asyncio
async def test_require_thread_and_project_access(db_session: AsyncSession) -> None:
	user = User(
		email="authz@example.com",
		username="authz_test",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add(user)
	await db_session.commit()
	principal = Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)

	with pytest.raises(HTTPException):
		await authorization.require_thread_access(
			new_typeid("thread"), db_session, principal=principal
		)

	with pytest.raises(HTTPException):
		await authorization.require_project_access(
			new_typeid("proj"), db_session, principal=principal
		)


def test_require_permission_denied() -> None:
	user = User(
		email="authz-deny@example.com",
		username="authz_deny",
		hashed_password="pw",
		is_active=True,
	)
	principal = Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)
	with pytest.raises(HTTPException):
		authorization.require_permission(principal, "agents:manage")


def test_require_permission_allows() -> None:
	user = User(
		email="authz-allow@example.com",
		username="authz_allow",
		hashed_password="pw",
		is_active=True,
	)
	principal = Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset({"agents:manage"}),
		role_resource_defaults=DefaultResourceAccess(),
	)

	authorization.require_permission(principal, "agents:manage")


@pytest.mark.asyncio
async def test_require_thread_access_hidden_forbidden(db_session: AsyncSession) -> None:
	user = User(
		email="authz-hidden@example.com",
		username="authz_hidden",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add(user)
	await db_session.commit()
	principal = Principal(
		user=user,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)

	with pytest.raises(HTTPException) as exc:
		await authorization.require_thread_access(
			TypeID("thread"),
			db_session,
			principal=principal,
			include_hidden=True,
		)
	assert exc.value.status_code == 403


def test_allowed_levels_reader_case() -> None:
	assert authorization._allowed_levels(AccessLevel.READER) == (
		AccessLevel.READER,
		AccessLevel.EDITOR,
		AccessLevel.ADMIN,
	)


@pytest.mark.asyncio
async def test_authorization_admin_predicates(db_session: AsyncSession) -> None:
	admin = User(
		email="authz-admin@example.com",
		username="authz_admin",
		hashed_password="pw",
		is_active=True,
		is_superuser=True,
	)
	db_session.add(admin)
	await db_session.commit()
	principal = Principal(
		user=admin,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)

	assert authorization._allowed_levels(AccessLevel.ADMIN) == (AccessLevel.ADMIN,)
	visibility = Thread.deleted_at.is_(None)
	assert authorization.thread_access_predicate(principal).compare(visibility)
	assert authorization.thread_access_predicate(
		principal, include_hidden=True
	).compare(true())
	assert authorization.project_access_predicate(principal).compare(true())
