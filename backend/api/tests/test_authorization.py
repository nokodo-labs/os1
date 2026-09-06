"""Tests for authorization helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.calendar import Calendar, CalendarEvent
from api.models.message import UserMessage
from api.models.reminder import Reminder, ReminderList
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ActionPermission, DefaultResourceAccess, ResourceType
from api.tests.factories import create_user, make_principal
from api.v1.service import vectorize as vectorize_service
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES,
	CONTAINED_LEVELS,
	LEAF_RESOURCE_TYPES,
	READ_ONLY_LEVELS,
	RESOURCE_CONFIG,
	VECTOR_CHUNK_ACCESS_RESOURCE_TYPES,
	VECTOR_CHUNK_PARENT_RESOURCE_TYPES,
	allowed_levels,
	apply_resource_access_list_filters,
	list_accessible_user_ids_for_resources,
	require_permission,
	require_project_access,
	require_thread_access,
	resolve_accessible_user_ids,
	resolve_resource_access_user_ids,
	resource_access_predicate,
	vector_acl_filter,
)
from api.v1.service.authorization import cache as authorization_cache
from api.v1.service.authorization import resolve as authorization_resolve
from api.v1.service.authorization.config import MAX_INHERITANCE_DEPTH
from api.v1.service.authorization.inheritance import (
	RESOURCE_PARENT_LINKS,
	ParentResourceRef,
)
from api.v1.service.vectorstores import VectorChunkResourceType
from nokodo_ai.adapters.base.vectorstores import FieldMatch, FieldMatchAny
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.mark.asyncio
async def test_default_editor_is_floor_for_explicit_reader(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""resolved SQL access keeps defaults as a floor below named grants."""
	from api.settings import settings

	owner = User(
		email=f"default_owner_{uuid4().hex}@example.com",
		username=f"default_owner_{uuid4().hex[:12]}",
		hashed_password="x",
		is_active=True,
	)
	reader = User(
		email=f"default_reader_{uuid4().hex}@example.com",
		username=f"default_reader_{uuid4().hex[:12]}",
		hashed_password="x",
		is_active=True,
	)
	db_session.add_all([owner, reader])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="default override")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=reader.id,
			level=AccessLevel.READER,
			order_index=0,
		)
	)
	await db_session.commit()
	defaults = settings.default_permissions.model_copy(deep=True)
	defaults.resource_access.thread = AccessLevel.EDITOR
	monkeypatch.setattr(settings, "default_permissions", defaults)
	resolved = await resolve_accessible_user_ids(
		ResourceType.THREAD,
		thread.id,
		db_session,
		required_level=AccessLevel.EDITOR,
	)
	assert reader.id in resolved
	principal = Principal.for_user(
		reader,
		role_resource_defaults=DefaultResourceAccess(thread=AccessLevel.EDITOR),
	)
	matched = await db_session.scalar(
		select(Thread.id).where(
			Thread.id == thread.id,
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				AccessLevel.EDITOR,
			),
		)
	)
	assert matched == thread.id


@pytest.mark.asyncio
async def test_resource_list_filters_use_relationship_and_exact_level(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email=f"list-owner-{uuid4().hex}@example.com",
		username=f"list_owner_{uuid4().hex[:12]}",
		hashed_password="pw",
		is_active=True,
	)
	reader = User(
		email=f"list-reader-{uuid4().hex}@example.com",
		username=f"list_reader_{uuid4().hex[:12]}",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add_all([owner, reader])
	await db_session.flush()
	owned = Thread(owner_id=reader.id, title="owned admin")
	shared_reader = Thread(owner_id=owner.id, title="shared reader")
	shared_editor = Thread(owner_id=owner.id, title="shared editor")
	db_session.add_all([owned, shared_reader, shared_editor])
	await db_session.flush()
	db_session.add_all(
		[
			AccessRule(
				thread_id=shared_reader.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
			AccessRule(
				thread_id=shared_editor.id,
				subject_user_id=reader.id,
				level=AccessLevel.EDITOR,
			),
		]
	)
	await db_session.flush()
	principal = Principal.for_user(reader)

	owned_stmt = apply_resource_access_list_filters(
		select(Thread.id), principal, ResourceType.THREAD, "owned", None
	)
	assert set(await db_session.scalars(owned_stmt)) == {owned.id}

	shared_stmt = apply_resource_access_list_filters(
		select(Thread.id), principal, ResourceType.THREAD, "shared", None
	)
	assert set(await db_session.scalars(shared_stmt)) == {
		shared_reader.id,
		shared_editor.id,
	}

	reader_stmt = apply_resource_access_list_filters(
		select(Thread.id), principal, ResourceType.THREAD, None, AccessLevel.READER
	)
	assert set(await db_session.scalars(reader_stmt)) == {shared_reader.id}

	editor_stmt = apply_resource_access_list_filters(
		select(Thread.id), principal, ResourceType.THREAD, None, AccessLevel.EDITOR
	)
	assert set(await db_session.scalars(editor_stmt)) == {shared_editor.id}

	admin_stmt = apply_resource_access_list_filters(
		select(Thread.id), principal, ResourceType.THREAD, None, AccessLevel.ADMIN
	)
	assert set(await db_session.scalars(admin_stmt)) == {owned.id}


def test_vector_acl_filter_excludes_subjectless_access() -> None:
	principal = make_principal("vector_public")
	acl = vector_acl_filter([VectorChunkResourceType.THREAD], principal)
	assert all(condition.key != "public_access" for condition in acl.any_of)


@pytest.mark.asyncio
async def test_subjectless_rule_is_direct_fetch_only(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email=f"link_owner_{uuid4().hex}@example.com",
		username=f"link_owner_{uuid4().hex[:12]}",
		hashed_password="x",
		is_active=True,
	)
	viewer = User(
		email=f"link_viewer_{uuid4().hex}@example.com",
		username=f"link_viewer_{uuid4().hex[:12]}",
		hashed_password="x",
		is_active=True,
	)
	db_session.add_all([owner, viewer])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="link-only thread")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(AccessRule(thread_id=thread.id, level=AccessLevel.READER))
	await db_session.flush()
	principal = Principal.for_user(
		user=viewer,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		global_action_permissions=frozenset(),
	)

	await require_thread_access(thread.id, db_session, principal)
	listed = await db_session.scalar(
		select(Thread.id).where(
			resource_access_predicate(principal, ResourceType.THREAD)
		)
	)
	assert listed is None
	assert viewer.id not in await resolve_resource_access_user_ids(
		ResourceType.THREAD,
		thread.id,
		db_session,
	)


def test_direct_default_skips_vector_acl_but_ancestor_default_does_not() -> None:
	direct = make_principal("vector_direct")
	direct = replace(
		direct,
		role_resource_defaults=DefaultResourceAccess(thread=AccessLevel.READER),
	)
	direct_filter = vector_acl_filter([VectorChunkResourceType.THREAD], direct)
	assert direct_filter.any_of == []

	ancestor = make_principal("vector_ancestor")
	ancestor = replace(
		ancestor,
		role_resource_defaults=DefaultResourceAccess(thread=AccessLevel.READER),
	)
	ancestor_filter = vector_acl_filter([VectorChunkResourceType.NOTE], ancestor)
	assert ancestor_filter.any_of


def test_vector_chunk_acl_mappings_are_plural_and_parent_aware() -> None:
	assert (
		VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[VectorChunkResourceType.FILE]
		== ResourceType.FILE
	)
	assert (
		VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[VectorChunkResourceType.FILE_CONTENT]
		== ResourceType.FILE
	)
	assert ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES[ResourceType.FILE] == (
		VectorChunkResourceType.FILE,
		VectorChunkResourceType.FILE_CONTENT,
	)
	assert (
		VECTOR_CHUNK_PARENT_RESOURCE_TYPES[VectorChunkResourceType.FILE_CONTENT]
		== VectorChunkResourceType.FILE
	)
	for (
		access_resource_type,
		chunk_resource_types,
	) in ACL_SYNC_VECTOR_CHUNK_RESOURCE_TYPES.items():
		for chunk_resource_type in chunk_resource_types:
			assert (
				VECTOR_CHUNK_ACCESS_RESOURCE_TYPES[chunk_resource_type]
				== access_resource_type
			)


def test_acl_sync_chunk_filters_split_direct_and_parented_file_chunks() -> None:
	filters = vectorize_service._acl_sync_chunk_filters(ResourceType.FILE, "file-1")
	assert len(filters) == 2
	direct_filter = next(
		chunk_filter
		for chunk_filter in filters
		if any(
			isinstance(match, FieldMatch)
			and match.key == "resource_id"
			and match.value == "file-1"
			for match in chunk_filter.all_of
		)
	)
	parent_filter = next(
		chunk_filter
		for chunk_filter in filters
		if any(
			isinstance(match, FieldMatch)
			and match.key == "parent_resource_id"
			and match.value == "file-1"
			for match in chunk_filter.all_of
		)
	)
	direct_type = next(
		match
		for match in direct_filter.all_of
		if isinstance(match, FieldMatch) and match.key == "resource_type"
	)
	assert direct_type.value == VectorChunkResourceType.FILE.value
	parent_types = {
		match.key: match.value
		for match in parent_filter.all_of
		if isinstance(match, FieldMatch)
	}
	assert parent_types == {
		"resource_type": VectorChunkResourceType.FILE_CONTENT.value,
		"parent_resource_type": VectorChunkResourceType.FILE.value,
		"parent_resource_id": "file-1",
	}
	assert not any(isinstance(match, FieldMatchAny) for match in parent_filter.all_of)


def test_acl_sync_chunk_filters_ignore_unaddressable_acl_resources() -> None:
	assert (
		vectorize_service._acl_sync_chunk_filters(ResourceType.CALENDAR, "cal-1") == []
	)


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
	principal = Principal.for_user(
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
	principal = make_principal(slug="authz_deny")
	with pytest.raises(HTTPException):
		require_permission(principal, ActionPermission.AGENTS_MANAGE)


def test_require_permission_allows() -> None:
	principal = make_principal(
		slug="authz_allow",
		permissions=frozenset({ActionPermission.AGENTS_MANAGE}),
	)

	require_permission(principal, ActionPermission.AGENTS_MANAGE)


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
	principal = Principal.for_user(
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
			include_deleted=True,
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
	) -> list[ParentResourceRef]:
		assert session is db_session
		return [
			ParentResourceRef(
				parent_type=resource_type,
				parent_id=resource_id,
				inherited_levels=CONTAINED_LEVELS,
			)
		]

	monkeypatch.setattr(
		authorization_cache,
		"load_parent_resource_refs",
		cyclic_parent_refs,
	)

	user_ids = await authorization_cache.resolve_accessible_user_ids(
		ResourceType.THREAD,
		thread.id,
		db_session,
	)

	assert set(user_ids) == {owner.id}


@pytest.mark.asyncio
async def test_cycle_truncation_is_not_memoised_for_later_refs(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a `[]` returned by the cycle break may not become a memoised answer.

	the callers still on the stack when the cycle breaks folded a truncation
	into their own results. without the guard the FIRST of them memoises that
	partial set, and the next top-level ref sharing the memo reads it as the
	final answer - a user silently loses access.
	"""
	owner_a = await create_user(db_session, "authz-cycle-memo-a")
	owner_b = await create_user(db_session, "authz-cycle-memo-b")
	thread_a = Thread(owner_id=owner_a.id, title="cycle memo a")
	thread_b = Thread(owner_id=owner_b.id, title="cycle memo b")
	db_session.add_all([thread_a, thread_b])
	await db_session.flush()

	# a two-node cycle: a's parent is b, b's parent is a
	partners = {thread_a.id: thread_b.id, thread_b.id: thread_a.id}

	async def cyclic_parent_refs(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[ParentResourceRef]:
		assert session is db_session
		return [
			ParentResourceRef(
				parent_type=resource_type,
				parent_id=partners[resource_id],
				inherited_levels=CONTAINED_LEVELS,
			)
		]

	monkeypatch.setattr(
		authorization_cache,
		"load_parent_resource_refs",
		cyclic_parent_refs,
	)

	# b first, so a is the frame that folds in the truncated answer
	shared_memo: dict[
		tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
	] = {}
	await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		thread_b.id,
		db_session,
		resolved_user_ids=shared_memo,
	)
	reused = await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		thread_a.id,
		db_session,
		resolved_user_ids=shared_memo,
	)
	fresh = await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		thread_a.id,
		db_session,
	)

	assert set(fresh) == {owner_a.id, owner_b.id}
	assert set(reused) == set(fresh), "a truncated result was memoised and reused"


@pytest.mark.asyncio
async def test_depth_truncation_is_not_memoised_for_later_refs(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the depth bound truncates the same way a cycle does, so it guards alike.

	a frame that hit `MAX_INHERITANCE_DEPTH` saw only part of its ancestry. a
	shallower ref starting from the same node reaches further, so memoising the
	deep frame's partial answer would hand that ref a smaller set than it earns.
	"""
	owner = await create_user(db_session, "authz-depth-memo-owner")
	viewer = await create_user(db_session, "authz-depth-memo-viewer")
	# longer than the bound, so a walk from the head truncates before the tail
	chain = [
		Thread(owner_id=owner.id, title=f"depth memo {index}")
		for index in range(MAX_INHERITANCE_DEPTH + 2)
	]
	db_session.add_all(chain)
	await db_session.flush()
	# only the tail grants the viewer, and only a shallow start can reach it
	db_session.add(
		AccessRule(
			thread_id=chain[-1].id,
			subject_user_id=viewer.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()

	parent_of = {
		thread.id: chain[index + 1].id for index, thread in enumerate(chain[:-1])
	}

	async def chained_parent_refs(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[ParentResourceRef]:
		assert session is db_session
		parent_id = parent_of.get(resource_id)
		if parent_id is None:
			return []
		return [
			ParentResourceRef(
				parent_type=resource_type,
				parent_id=parent_id,
				inherited_levels=CONTAINED_LEVELS,
			)
		]

	monkeypatch.setattr(
		authorization_cache,
		"load_parent_resource_refs",
		chained_parent_refs,
	)

	# from the head the walk stops short of the tail's rule
	shared_memo: dict[
		tuple[ResourceType, TypeID, AccessLevel, bool, bool], frozenset[TypeID]
	] = {}
	truncated = await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		chain[0].id,
		db_session,
		resolved_user_ids=shared_memo,
	)
	assert viewer.id not in set(truncated), "the chain is not long enough to truncate"

	# two hops in, the tail IS within the bound, so the viewer must appear
	reused = await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		chain[2].id,
		db_session,
		resolved_user_ids=shared_memo,
	)
	fresh = await authorization_cache.resolve_resource_access_user_ids(
		ResourceType.THREAD,
		chain[2].id,
		db_session,
	)

	assert viewer.id in set(fresh)
	assert set(reused) == set(fresh), "a depth-truncated result was memoised"


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
	principal = Principal.for_user(
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
	) -> list[ParentResourceRef]:
		assert session is db_session
		return [
			ParentResourceRef(
				parent_type=resource_type,
				parent_id=resource_id,
				inherited_levels=CONTAINED_LEVELS,
			)
		]

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
async def test_effective_access_reuses_shared_ancestor_level(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = User(
		email="authz-diamond-owner@example.com",
		username="authz_diamond_owner",
		hashed_password="pw",
		is_active=True,
	)
	viewer = User(
		email="authz-diamond-viewer@example.com",
		username="authz_diamond_viewer",
		hashed_password="pw",
		is_active=True,
	)
	db_session.add_all([owner, viewer])
	await db_session.flush()
	root = Thread(owner_id=owner.id, title="diamond root")
	weak_parent = Thread(owner_id=owner.id, title="diamond weak")
	strong_parent = Thread(owner_id=owner.id, title="diamond strong")
	child = Thread(owner_id=owner.id, title="diamond child")
	db_session.add_all([root, weak_parent, strong_parent, child])
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=root.id,
			subject_user_id=viewer.id,
			level=AccessLevel.ADMIN,
		)
	)
	await db_session.flush()
	principal = Principal.for_user(viewer)

	async def diamond_parent_refs(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[ParentResourceRef]:
		assert resource_type == ResourceType.THREAD
		assert session is db_session
		if resource_id == child.id:
			return [
				ParentResourceRef(
					parent_type=ResourceType.THREAD,
					parent_id=weak_parent.id,
					inherited_levels=READ_ONLY_LEVELS,
				),
				ParentResourceRef(
					parent_type=ResourceType.THREAD,
					parent_id=strong_parent.id,
					inherited_levels=CONTAINED_LEVELS,
				),
			]
		if resource_id in {weak_parent.id, strong_parent.id}:
			return [
				ParentResourceRef(
					parent_type=ResourceType.THREAD,
					parent_id=root.id,
					inherited_levels=CONTAINED_LEVELS,
				)
			]
		return []

	monkeypatch.setattr(
		authorization_resolve,
		"load_parent_resource_refs",
		diamond_parent_refs,
	)
	level = await authorization_resolve.get_effective_access_level(
		db_session,
		principal,
		ResourceType.THREAD,
		child.id,
	)
	assert level == AccessLevel.ADMIN


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
	principal = Principal.for_user(
		user=admin,
		group_ids=(),
		role_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)

	assert allowed_levels(AccessLevel.ADMIN) == (AccessLevel.ADMIN,)
	assert resource_access_predicate(principal, ResourceType.THREAD).compare(true())
	assert resource_access_predicate(principal, ResourceType.PROJECT).compare(true())


@pytest.mark.asyncio
async def test_vector_acl_sync_patches_only_the_named_resources(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""no descendant walk: descendants repair through the ACL staleness sweep."""
	project_id = new_typeid("proj")
	calls: list[tuple[ResourceType, list[str]]] = []

	async def record_payloads(
		resource_ids: list[str],
		resource_type: ResourceType,
		session: AsyncSession,
	) -> None:
		assert session is db_session
		calls.append((resource_type, resource_ids))

	monkeypatch.setattr(
		vectorize_service, "_sync_resource_vector_acl_payloads", record_payloads
	)

	await vectorize_service.sync_resource_refs_vector_acl(
		[(ResourceType.PROJECT, project_id)], db_session
	)

	assert calls == [(ResourceType.PROJECT, [str(project_id)])]


@pytest.mark.asyncio
async def test_thread_descendants_include_messages_and_member_is_accessible(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email=f"descendant-owner-{uuid4().hex}@example.com",
		username=f"do_{uuid4().hex[:12]}",
		hashed_password="pw",
	)
	member = User(
		email=f"descendant-member-{uuid4().hex}@example.com",
		username=f"dm_{uuid4().hex[:12]}",
		hashed_password="pw",
	)
	db_session.add_all([owner, member])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title="message descendant")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	db_session.add(message)
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=member.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()

	assert member.id in await list_accessible_user_ids_for_resources(
		[(ResourceType.MESSAGE, message.id)], db_session
	)


def test_every_leaf_config_has_matching_parent_link() -> None:
	assert LEAF_RESOURCE_TYPES
	for child_type in LEAF_RESOURCE_TYPES:
		config = RESOURCE_CONFIG[child_type]
		assert any(
			link.child_type == child_type and link.parent_type == config.parent_type
			for link in RESOURCE_PARENT_LINKS
		)


@pytest.mark.asyncio
async def test_each_leaf_type_is_reachable_from_its_parent(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email=f"leaf-reach-owner-{uuid4().hex}@example.com",
		username=f"lro_{uuid4().hex[:12]}",
		hashed_password="pw",
	)
	db_session.add(owner)
	await db_session.flush()

	thread = Thread(owner_id=owner.id, title="leaf reachability")
	reminder_list = ReminderList(owner_id=owner.id, name=f"reach {uuid4().hex}")
	calendar = Calendar(owner_id=owner.id, name=f"reach {uuid4().hex}")
	db_session.add_all([thread, reminder_list, calendar])
	await db_session.flush()
	message = UserMessage(thread_id=thread.id, sender_user_id=owner.id)
	reminder = Reminder(
		owner_id=owner.id,
		list_id=reminder_list.id,
		title="reachable reminder",
	)
	start_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
	event = CalendarEvent(
		owner_id=owner.id,
		calendar_id=calendar.id,
		title="reachable event",
		start_at=start_at,
		end_at=start_at + timedelta(hours=1),
	)
	db_session.add_all([message, reminder, event])
	await db_session.flush()

	# reachability is asserted upward now, through the surviving parent walk:
	# every leaf must resolve its parent's owner as an accessible user.
	for leaf_type, leaf_id in (
		(ResourceType.MESSAGE, message.id),
		(ResourceType.REMINDER, reminder.id),
		(ResourceType.CALENDAR_EVENT, event.id),
	):
		assert owner.id in await list_accessible_user_ids_for_resources(
			[(leaf_type, leaf_id)], db_session
		), f"{leaf_type.value} does not inherit from its parent"
