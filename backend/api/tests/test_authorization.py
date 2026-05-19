"""Tests for authorization helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import true
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.thread import Thread
from api.models.user import User
from api.permissions import DefaultResourceAccess, ResourceType
from api.v1.service import vectorize as vectorize_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	allowed_levels,
	project_access_predicate,
	require_permission,
	require_project_access,
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.authorization import cache as authorization_cache
from api.v1.service.authorization import resolve as authorization_resolve
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
		await require_thread_access(
			new_typeid("thread"), db_session, principal=principal
		)

	with pytest.raises(HTTPException):
		await require_project_access(
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
		require_permission(principal, "agents:manage")


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

	require_permission(principal, "agents:manage")


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
		await require_thread_access(
			TypeID("thread"),
			db_session,
			principal=principal,
			include_hidden=True,
		)
	assert exc.value.status_code == 403


def test_allowed_levels_reader_case() -> None:
	assert allowed_levels(AccessLevel.READER) == (
		AccessLevel.READER,
		AccessLevel.EDITOR,
		AccessLevel.ADMIN,
	)


@pytest.mark.asyncio
async def test_accessible_user_expansion_ignores_parent_cycles(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = User(
		email="authz-cycle-owner@example.com",
		username="authz_cycle_owner",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="cycle cache")
	db_session.add(thread)
	await db_session.flush()

	async def cyclic_parent_refs(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[tuple[ResourceType, TypeID]]:
		assert session is db_session
		return [(resource_type, resource_id)]

	monkeypatch.setattr(
		authorization_cache,
		"load_parent_resource_refs",
		cyclic_parent_refs,
	)

	user_ids = await authorization_cache._list_accessible_user_ids_uncached(
		ResourceType.THREAD,
		thread.id,
		db_session,
	)

	assert set(user_ids) == {owner.id}


@pytest.mark.asyncio
async def test_effective_access_resolution_ignores_parent_cycles(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = User(
		email="authz-resolve-cycle-owner@example.com",
		username="authz_resolve_cycle_owner",
		hashed_password="pw",
		is_active=True,
	)
	viewer = User(
		email="authz-resolve-cycle-viewer@example.com",
		username="authz_resolve_cycle_viewer",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add_all([owner, viewer])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="cycle resolve")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=viewer.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()
	principal = Principal(
		user=viewer,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)

	async def cyclic_parent_refs(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[tuple[ResourceType, TypeID]]:
		assert session is db_session
		return [(resource_type, resource_id)]

	monkeypatch.setattr(
		authorization_resolve,
		"load_parent_resource_refs",
		cyclic_parent_refs,
	)

	level = await authorization_resolve.get_effective_access_level(
		db_session,
		principal,
		ResourceType.THREAD,
		thread.id,
	)

	assert level == AccessLevel.READER


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

	assert allowed_levels(AccessLevel.ADMIN) == (AccessLevel.ADMIN,)
	visibility = Thread.deleted_at.is_(None)
	assert thread_access_predicate(principal).compare(visibility)
	assert thread_access_predicate(principal, include_hidden=True).compare(true())
	assert project_access_predicate(principal).compare(true())


@pytest.mark.asyncio
async def test_vector_acl_sync_includes_inheriting_resources(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	project_id = new_typeid("proj")
	thread_id = new_typeid("thread")
	file_id = new_typeid("file")
	calls: list[tuple[ResourceType, list[str]]] = []

	async def record_payloads(
		resource_ids: list[str],
		resource_type: ResourceType,
		session: AsyncSession,
	) -> None:
		assert session is db_session
		calls.append((resource_type, resource_ids))

	async def load_descendants(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> dict[ResourceType, set[TypeID]]:
		assert resource_type == ResourceType.PROJECT
		assert resource_id == project_id
		assert session is db_session
		return {
			ResourceType.THREAD: {thread_id},
			ResourceType.FILE: {file_id},
		}

	monkeypatch.setattr(
		vectorize_service, "_sync_resource_vector_acl_payloads", record_payloads
	)
	monkeypatch.setattr(
		vectorize_service, "load_descendant_resource_ids", load_descendants
	)

	await vectorize_service.sync_resource_vector_acl(
		str(project_id), ResourceType.PROJECT, db_session
	)

	assert calls == [
		(ResourceType.PROJECT, [str(project_id)]),
		(ResourceType.THREAD, [str(thread_id)]),
		(ResourceType.FILE, [str(file_id)]),
	]
