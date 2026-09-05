"""per-user thread state filters across listing, search and vector payloads.

the same eight ``*_by`` / ``not_*_by`` params drive three layers:
- the SQL listing (``core.list_threads`` / ``count_threads``)
- the pg_trgm autocomplete search tier (SQL only)
- the qdrant tier, where they must be enforced NATIVELY as payload conditions

these tests lock in all three, plus the payload sync + backfill machinery that
keeps the vector fields in step with the participant rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.project import Project
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ActionPermission, DefaultResourceAccess, ResourceType
from api.schemas.search import SearchMode, SearchParams
from api.schemas.thread import ThreadListFilters, ThreadSearchFilters
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service.authentication import Principal
from api.v1.service.threads import core as thread_core
from api.v1.service.threads.search import (
	_autocomplete_threads,
	_thread_search_filter,
)
from api.v1.service.threads.user_state import (
	STATE_VECTORS_SCHEMA,
	STATE_VECTORS_SCHEMA_KEY,
	state_vectors_due_predicate,
	sync_thread_state_vectors,
	thread_state_vector_metadata,
	update_thread_participant,
)
from nokodo_ai.adapters.base.vectorstores import FieldCondition, FieldMatch
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import TypeID, new_typeid


_SPARSE = SearchParams(mode=SearchMode.SPARSE)


def _uid() -> str:
	return uuid4().hex[:8]


def _user(suffix: str) -> User:
	return User(
		email=f"{suffix}@state.test",
		username=f"state_{suffix}",
		hashed_password=hash_password("x"),
		is_active=True,
	)


def _principal(user: User, operator: bool = False) -> Principal:
	"""principal for a user; operators may read other users' private state."""
	return Principal.for_user(
		user=user,
		group_ids=(),
		permissions=frozenset(),
		global_action_permissions=(
			frozenset({ActionPermission.USERS_MANAGE}) if operator else frozenset()
		),
		role_resource_defaults=DefaultResourceAccess(),
	)


async def _flag(
	session: AsyncSession,
	thread: Thread,
	user: User,
	archived: bool = False,
	muted: bool = False,
	pinned: bool = False,
) -> None:
	"""set a user's state flags on a thread directly (no access checks)."""
	session.add(
		ThreadParticipant(
			thread_id=thread.id,
			user_id=user.id,
			archived=archived,
			muted=muted,
			pinned=pinned,
		)
	)
	await session.commit()


# --- SQL listing ------------------------------------------------------------


@pytest.mark.asyncio
async def test_listing_filters_by_named_user_state(db_session: AsyncSession) -> None:
	"""archived_by selects, not_archived_by excludes, no param means neither."""
	s = _uid()
	owner = _user(f"list_{s}")
	db_session.add(owner)
	await db_session.flush()

	archived = Thread(owner_id=owner.id, title=f"arch_{s}", is_temporary=False)
	plain = Thread(owner_id=owner.id, title=f"plain_{s}", is_temporary=False)
	db_session.add_all([archived, plain])
	await db_session.commit()
	await _flag(db_session, archived, owner, archived=True)

	principal = _principal(owner)

	async def _ids(filters: ThreadListFilters) -> set[str]:
		threads = await thread_core.list_threads(
			db_session, principal=principal, filters=filters
		)
		return {str(t.id) for t in threads}

	only_archived = ThreadListFilters(archived_by=TypeID(owner.id))
	not_archived = ThreadListFilters(not_archived_by=TypeID(owner.id))

	assert {str(archived.id), str(plain.id)} <= await _ids(ThreadListFilters())
	assert await _ids(only_archived) == {str(archived.id)}
	assert str(archived.id) not in await _ids(not_archived)
	assert str(plain.id) in await _ids(not_archived)


@pytest.mark.asyncio
async def test_listing_combines_filters_for_different_users(
	db_session: AsyncSession,
) -> None:
	"""different states may name different subjects in one query."""
	s = _uid()
	owner, other = _user(f"combo_{s}_a"), _user(f"combo_{s}_b")
	db_session.add_all([owner, other])
	await db_session.flush()

	match = Thread(owner_id=owner.id, title=f"match_{s}", is_temporary=False)
	miss = Thread(owner_id=owner.id, title=f"miss_{s}", is_temporary=False)
	db_session.add_all([match, miss])
	await db_session.commit()
	# owner pinned both; other archived only `miss`.
	await _flag(db_session, match, owner, pinned=True)
	await _flag(db_session, miss, owner, pinned=True)
	await _flag(db_session, miss, other, archived=True)

	# naming another user as a filter subject requires the operator gate.
	threads = await thread_core.list_threads(
		db_session,
		principal=_principal(owner, operator=True),
		filters=ThreadListFilters(
			pinned_by=TypeID(owner.id),
			not_archived_by=TypeID(other.id),
		),
	)
	ids = {str(t.id) for t in threads}
	assert str(match.id) in ids
	assert str(miss.id) not in ids


@pytest.mark.asyncio
async def test_count_honours_state_filters(db_session: AsyncSession) -> None:
	"""counting shares the filter path with listing."""
	s = _uid()
	owner = _user(f"count_{s}")
	db_session.add(owner)
	await db_session.flush()
	archived = Thread(owner_id=owner.id, title=f"c_arch_{s}", is_temporary=False)
	plain = Thread(owner_id=owner.id, title=f"c_plain_{s}", is_temporary=False)
	db_session.add_all([archived, plain])
	await db_session.commit()
	await _flag(db_session, archived, owner, archived=True)

	principal = _principal(owner)
	assert (
		await thread_core.count_threads(
			db_session,
			principal=principal,
			filters=ThreadListFilters(archived_by=TypeID(owner.id)),
		)
		== 1
	)
	assert (
		await thread_core.count_threads(
			db_session,
			principal=principal,
			filters=ThreadListFilters(not_archived_by=TypeID(owner.id)),
		)
		== 1
	)


@pytest.mark.asyncio
async def test_listing_filters_by_project(db_session: AsyncSession) -> None:
	"""project_id scopes the listing (parity with search)."""
	s = _uid()
	owner = _user(f"proj_{s}")
	db_session.add(owner)
	await db_session.flush()
	project = Project(owner_id=owner.id, name=f"proj_{s}")
	db_session.add(project)
	await db_session.flush()

	inside = Thread(owner_id=owner.id, title=f"in_{s}", is_temporary=False)
	inside.projects = [project]
	outside = Thread(owner_id=owner.id, title=f"out_{s}", is_temporary=False)
	db_session.add_all([inside, outside])
	await db_session.commit()

	threads = await thread_core.list_threads(
		db_session,
		principal=_principal(owner),
		filters=ThreadListFilters(project_id=TypeID(project.id)),
	)
	ids = {str(t.id) for t in threads}
	assert ids == {str(inside.id)}


# --- pg_trgm autocomplete tier ---------------------------------------------


@pytest.mark.asyncio
async def test_autocomplete_honours_state_filters(db_session: AsyncSession) -> None:
	"""the SQL search tier applies the same state filters as the listing."""
	s = _uid()
	owner = _user(f"auto_{s}")
	db_session.add(owner)
	await db_session.flush()
	archived = Thread(
		owner_id=owner.id, title=f"searchable_{s}_arch", is_temporary=False
	)
	plain = Thread(owner_id=owner.id, title=f"searchable_{s}_plain", is_temporary=False)
	db_session.add_all([archived, plain])
	await db_session.commit()
	await _flag(db_session, archived, owner, archived=True)

	principal = _principal(owner)
	results = await _autocomplete_threads(
		f"searchable_{s}",
		db_session,
		principal=principal,
		filters=ThreadSearchFilters(archived_by=TypeID(owner.id)),
	)
	assert {str(r.item.id) for r in results} == {str(archived.id)}

	results = await _autocomplete_threads(
		f"searchable_{s}",
		db_session,
		principal=principal,
		filters=ThreadSearchFilters(not_archived_by=TypeID(owner.id)),
	)
	assert {str(r.item.id) for r in results} == {str(plain.id)}


# --- qdrant tier: native conditions ----------------------------------------


def _matches(conditions: list[FieldCondition]) -> set[tuple[str, object]]:
	"""collapse field-match conditions to (key, value) pairs."""
	return {(c.key, c.value) for c in conditions if isinstance(c, FieldMatch)}


def test_search_filter_is_native_for_both_directions() -> None:
	"""state filters become payload conditions, negation via none_of."""
	me, other = new_typeid("user"), new_typeid("user")
	chunk_filter = _thread_search_filter(
		ThreadSearchFilters(
			archived_by=TypeID(me),
			not_invite_pending_for=TypeID(other),
			muted_by=TypeID(other),
		)
	)
	required = _matches(chunk_filter.all_of)
	assert ("archived_by", me) in required
	assert ("muted_by", other) in required
	assert ("invite_pending_to", other) in _matches(chunk_filter.none_of)


def test_search_filter_keeps_structured_conditions_native() -> None:
	"""owner and project stay vector-side conditions alongside state."""
	owner, project = new_typeid("user"), new_typeid("project")
	chunk_filter = _thread_search_filter(
		ThreadSearchFilters(
			owner_id=TypeID(owner),
			project_id=TypeID(project),
			not_archived_by=TypeID(owner),
		)
	)
	required = _matches(chunk_filter.all_of)
	assert ("owner_id", owner) in required
	assert ("project_ids", project) in required
	assert _matches(chunk_filter.none_of) == {("archived_by", owner)}


def test_search_filter_merges_into_the_acl_prefilter() -> None:
	"""merging preserves the ACL any_of group and ANDs the rest."""
	me = new_typeid("user")
	acl = vectorstores_service.acl_filter(
		[vectorstores_service.VectorChunkResourceType.THREAD],
		skip_principal_filter=False,
		user_id=me,
	)
	merged = vectorstores_service.merge_filters(
		acl,
		_thread_search_filter(ThreadSearchFilters(not_archived_by=TypeID(me))),
	)
	assert merged.any_of == acl.any_of
	assert len(merged.all_of) == len(acl.all_of)
	assert _matches(merged.none_of) == {("archived_by", me)}


def test_participant_scope_is_not_a_vector_condition() -> None:
	"""scope means "has other writers"; the acl payload has no levels."""
	chunk_filter = _thread_search_filter(
		ThreadSearchFilters(participant_scope="people")
	)
	keys = {c.key for c in chunk_filter.all_of} | {c.key for c in chunk_filter.none_of}
	assert "participant_scope" not in keys


# --- vector payload sync ----------------------------------------------------


@pytest.mark.asyncio
async def test_state_metadata_lists_flagging_users(db_session: AsyncSession) -> None:
	"""each payload field lists exactly the users with that flag set."""
	s = _uid()
	owner, other = _user(f"meta_{s}_a"), _user(f"meta_{s}_b")
	db_session.add_all([owner, other])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"meta_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.commit()
	await _flag(db_session, thread, owner, archived=True, muted=True)
	await _flag(db_session, thread, other, pinned=True)

	metadata = await thread_state_vector_metadata(db_session, [thread.id])
	entry = metadata[str(thread.id)]
	assert entry["archived_by"] == [str(owner.id)]
	assert entry["muted_by"] == [str(owner.id)]
	assert entry["pinned_by"] == [str(other.id)]
	assert entry["invite_pending_to"] == []


@pytest.mark.asyncio
async def test_state_sync_patches_payload_and_stamps_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""syncing patches vector payloads and records the layout version."""
	s = _uid()
	owner = _user(f"sync_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"sync_{s}", is_temporary=False)
	# the stamp is a SQL-side jsonb merge; both halves must survive it.
	thread.set_metadata(public={"topic": "x"}, private={"sibling": "keep"})
	db_session.add(thread)
	await db_session.commit()
	await _flag(db_session, thread, owner, archived=True)

	patched: list[Mapping[str, object]] = []

	async def _capture(
		resource_ids: list[str],
		resource_type: ResourceType,
		payload_by_id: Mapping[str, Mapping[str, object]],
		session: AsyncSession,
	) -> None:
		assert resource_type is ResourceType.THREAD
		patched.extend(payload_by_id[rid] for rid in resource_ids)

	monkeypatch.setattr(
		"api.v1.service.threads.user_state.sync_resource_vector_payload", _capture
	)
	await sync_thread_state_vectors(db_session, [thread.id])

	assert patched and patched[0]["archived_by"] == [str(owner.id)]
	await db_session.refresh(thread)
	assert thread.private_metadata.get(STATE_VECTORS_SCHEMA_KEY) == STATE_VECTORS_SCHEMA
	assert thread.private_metadata["sibling"] == "keep"
	assert thread.public_metadata == {"topic": "x"}


@pytest.mark.asyncio
async def test_state_change_triggers_payload_sync(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""archiving a thread re-syncs its searchable state immediately."""
	s = _uid()
	owner = _user(f"trigger_{s}")
	db_session.add(owner)
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"trigger_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	db_session.add(ThreadParticipant(thread_id=thread.id, user_id=owner.id))
	await db_session.commit()

	synced: list[str] = []

	async def _capture(session: AsyncSession, thread_ids: list[object]) -> None:
		synced.extend(str(tid) for tid in thread_ids)

	monkeypatch.setattr(
		"api.v1.service.threads.user_state.sync_thread_state_vectors", _capture
	)
	await update_thread_participant(
		db_session,
		_principal(owner),
		TypeID(thread.id),
		TypeID(owner.id),
		archived=True,
	)
	assert str(thread.id) in synced


@pytest.mark.asyncio
async def test_unstamped_threads_are_due_for_backfill(
	db_session: AsyncSession,
) -> None:
	"""the sweep predicate selects threads with a missing or stale stamp."""
	s = _uid()
	owner = _user(f"due_{s}")
	db_session.add(owner)
	await db_session.flush()
	fresh = Thread(owner_id=owner.id, title=f"fresh_{s}", is_temporary=False)
	fresh.set_metadata(private={STATE_VECTORS_SCHEMA_KEY: STATE_VECTORS_SCHEMA})
	stale = Thread(owner_id=owner.id, title=f"stale_{s}", is_temporary=False)
	stale.set_metadata(private={STATE_VECTORS_SCHEMA_KEY: STATE_VECTORS_SCHEMA - 1})
	never = Thread(owner_id=owner.id, title=f"never_{s}", is_temporary=False)
	db_session.add_all([fresh, stale, never])
	await db_session.commit()

	due = {
		str(row[0])
		for row in await db_session.execute(
			select(Thread.id).where(
				Thread.id.in_([fresh.id, stale.id, never.id]),
				state_vectors_due_predicate(),
			)
		)
	}
	assert due == {str(stale.id), str(never.id)}


@pytest.mark.asyncio
async def test_membership_change_syncs_state_payload(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""removing a member drops their state and re-syncs the payload."""
	s = _uid()
	owner, member = _user(f"mem_{s}_a"), _user(f"mem_{s}_b")
	db_session.add_all([owner, member])
	await db_session.flush()
	thread = Thread(owner_id=owner.id, title=f"mem_{s}", is_temporary=False)
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			subject_user_id=member.id,
			thread_id=thread.id,
			level=AccessLevel.EDITOR,
			order_index=0,
		)
	)
	await db_session.commit()
	await _flag(db_session, thread, member, archived=True)

	synced: list[str] = []

	async def _capture(session: AsyncSession, thread_ids: list[object]) -> None:
		synced.extend(str(tid) for tid in thread_ids)

	monkeypatch.setattr(
		"api.v1.service.threads.members.sync_thread_state_vectors", _capture
	)
	from api.v1.service.threads.members import remove_member

	await remove_member(
		db_session,
		_principal(owner),
		TypeID(thread.id),
		user_id=TypeID(member.id),
	)
	assert str(thread.id) in synced
	metadata = await thread_state_vector_metadata(db_session, [thread.id])
	assert metadata[str(thread.id)]["archived_by"] == []
