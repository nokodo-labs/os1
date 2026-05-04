"""security tests: search must never leak data across users/tenants.

tests cover all three search tiers:
- pg_trgm autocomplete (pure postgres)
- qdrant hybrid search with postgres post-filter (defense-in-depth)

key invariant: regardless of what the vector layer returns, the postgres
re-validation step must prevent cross-user results from ever reaching the caller.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.note import Note
from api.models.reminder import Reminder, ReminderList
from api.models.thread import Thread
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.schemas.search import SearchMode, SearchParams
from api.v1.service import notes as notes_service
from api.v1.service import vectorstores as vectorstores_service
from api.v1.service.auth import Principal
from api.v1.service.reminders.search import (
	_autocomplete_reminders,
	_hybrid_search_reminders,
)
from api.v1.service.threads.search import _autocomplete_threads, _hybrid_search_threads
from nokodo_ai.adapters.base.vectorstores import ChunkSearchResult
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import TypeID


# --- helpers ---


def _uid() -> str:
	return uuid4().hex[:8]


def _user(suffix: str, superuser: bool = False) -> User:
	return User(
		email=f"{suffix}@iso.test",
		username=f"iso_{suffix}",
		hashed_password=hash_password("x"),
		is_active=True,
		is_superuser=superuser,
	)


def _principal(user: User) -> Principal:
	return Principal(
		user=user,
		group_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)


def _reminder_list(owner: User, suffix: str) -> ReminderList:
	return ReminderList(
		owner_id=TypeID(owner.id),
		name=f"list_{suffix}",
		color="#22c55e",
	)


_AUTOCOMPLETE = SearchParams(mode=SearchMode.AUTOCOMPLETE)
_SPARSE = SearchParams(mode=SearchMode.SPARSE)


def _fake_search_fn(
	*resource_ids: str,
) -> object:
	"""return a fake vectorstore search that yields the given resource IDs."""

	async def _search(**_kwargs: object) -> list[ChunkSearchResult]:
		return [
			ChunkSearchResult(
				id=rid,
				metadata={"resource_id": rid, "resource_type": "?"},
				score=0.9,
			)
			for rid in resource_ids
		]

	return _search


# ================================================================
# notes - autocomplete (pg_trgm)
# ================================================================


@pytest.mark.asyncio
async def test_notes_autocomplete_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	"""user A must not find user B's note via pg_trgm autocomplete."""
	s = _uid()
	u_a, u_b = _user(f"na_{s}_a"), _user(f"na_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	note_b = Note(
		user_id=str(u_b.id), title=f"private_note_{s}", content="secret content"
	)
	db_session.add(note_b)
	await db_session.commit()

	results = await notes_service._autocomplete_notes(
		note_b.title, db_session, principal=_principal(u_a)
	)
	assert not any(str(r.id) == str(note_b.id) for r in results), (
		"cross-user note appeared in pg_trgm autocomplete"
	)


@pytest.mark.asyncio
async def test_notes_autocomplete_returns_own_note(
	db_session: AsyncSession,
) -> None:
	"""user A must find their own note via pg_trgm autocomplete."""
	s = _uid()
	u_a = _user(f"na_own_{s}")
	db_session.add(u_a)
	await db_session.flush()

	note_a = Note(
		user_id=str(u_a.id), title=f"my_unique_note_{s}", content="my content"
	)
	db_session.add(note_a)
	await db_session.commit()

	results = await notes_service._autocomplete_notes(
		note_a.title, db_session, principal=_principal(u_a)
	)
	ids = [str(r.id) for r in results]
	assert str(note_a.id) in ids, "user's own note not returned by autocomplete"


@pytest.mark.asyncio
async def test_notes_autocomplete_admin_sees_all(
	db_session: AsyncSession,
) -> None:
	"""admin principal must be able to see any user's notes."""
	s = _uid()
	owner = _user(f"na_owner_{s}")
	admin = _user(f"na_admin_{s}", superuser=True)
	db_session.add_all([owner, admin])
	await db_session.flush()

	note = Note(
		user_id=str(owner.id), title=f"admin_visible_note_{s}", content="content"
	)
	db_session.add(note)
	await db_session.commit()

	results = await notes_service._autocomplete_notes(
		note.title, db_session, principal=_principal(admin)
	)
	ids = [str(r.id) for r in results]
	assert str(note.id) in ids, "admin could not see another user's note"


@pytest.mark.asyncio
async def test_notes_autocomplete_soft_deleted_excluded(
	db_session: AsyncSession,
) -> None:
	"""soft-deleted notes must not appear in autocomplete results."""
	s = _uid()
	u = _user(f"na_del_{s}")
	db_session.add(u)
	await db_session.flush()

	note = Note(user_id=str(u.id), title=f"deleted_note_{s}", content="gone")
	db_session.add(note)
	await db_session.flush()
	note.soft_delete()
	await db_session.commit()

	results = await notes_service._autocomplete_notes(
		note.title, db_session, principal=_principal(u)
	)
	assert not any(str(r.id) == str(note.id) for r in results), (
		"soft-deleted note appeared in autocomplete"
	)


# ================================================================
# threads - autocomplete (pg_trgm)
# ================================================================


@pytest.mark.asyncio
async def test_threads_autocomplete_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	"""user A must not find user B's thread via pg_trgm autocomplete."""
	s = _uid()
	u_a, u_b = _user(f"ta_{s}_a"), _user(f"ta_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	thread_b = Thread(
		owner_id=TypeID(u_b.id), title=f"private_thread_{s}", is_temporary=False
	)
	db_session.add(thread_b)
	await db_session.commit()

	title = thread_b.title
	assert title is not None
	results = await _autocomplete_threads(title, db_session, principal=_principal(u_a))
	assert not any(str(r.id) == str(thread_b.id) for r in results), (
		"cross-user thread appeared in pg_trgm autocomplete"
	)


@pytest.mark.asyncio
async def test_threads_autocomplete_returns_own_thread(
	db_session: AsyncSession,
) -> None:
	"""user A must find their own thread via pg_trgm autocomplete."""
	s = _uid()
	u_a = _user(f"ta_own_{s}")
	db_session.add(u_a)
	await db_session.flush()

	thread_a = Thread(
		owner_id=TypeID(u_a.id),
		title=f"my_unique_thread_{s}",
		is_temporary=False,
	)
	db_session.add(thread_a)
	await db_session.commit()

	title = thread_a.title
	assert title is not None
	results = await _autocomplete_threads(title, db_session, principal=_principal(u_a))
	ids = [str(r.id) for r in results]
	assert str(thread_a.id) in ids, "user's own thread not returned by autocomplete"


@pytest.mark.asyncio
async def test_threads_autocomplete_granted_user_sees_thread(
	db_session: AsyncSession,
) -> None:
	"""user B with an explicit access rule must be able to find user A's thread."""
	s = _uid()
	u_a, u_b = _user(f"ta_share_{s}_a"), _user(f"ta_share_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	thread_a = Thread(
		owner_id=TypeID(u_a.id),
		title=f"shared_thread_{s}",
		is_temporary=False,
	)
	db_session.add(thread_a)
	await db_session.flush()

	rule = AccessRule(
		thread_id=str(thread_a.id),
		subject_user_id=TypeID(u_b.id),
		level=AccessLevel.READER,
	)
	db_session.add(rule)
	await db_session.commit()

	title = thread_a.title
	assert title is not None
	results = await _autocomplete_threads(title, db_session, principal=_principal(u_b))
	ids = [str(r.id) for r in results]
	assert str(thread_a.id) in ids, "grantee could not find explicitly shared thread"


@pytest.mark.asyncio
async def test_threads_autocomplete_temporary_threads_excluded(
	db_session: AsyncSession,
) -> None:
	"""temporary threads must not appear in autocomplete results even for owner."""
	s = _uid()
	u = _user(f"ta_tmp_{s}")
	db_session.add(u)
	await db_session.flush()

	tmp_thread = Thread(
		owner_id=TypeID(u.id),
		title=f"temp_thread_{s}",
		is_temporary=True,
	)
	db_session.add(tmp_thread)
	await db_session.commit()

	title = tmp_thread.title
	assert title is not None
	results = await _autocomplete_threads(title, db_session, principal=_principal(u))
	assert not any(str(r.id) == str(tmp_thread.id) for r in results), (
		"temporary thread appeared in autocomplete"
	)


# ================================================================
# reminders - autocomplete (pg_trgm)
# ================================================================


@pytest.mark.asyncio
async def test_reminders_autocomplete_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	"""user A must not find user B's reminder via pg_trgm autocomplete."""
	s = _uid()
	u_a, u_b = _user(f"ra_{s}_a"), _user(f"ra_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	list_b = _reminder_list(u_b, f"ra_{s}_b")
	db_session.add(list_b)
	await db_session.flush()

	rem_b = Reminder(
		owner_id=TypeID(u_b.id),
		list_id=list_b.id,
		title=f"private_reminder_{s}",
	)
	db_session.add(rem_b)
	await db_session.commit()

	results = await _autocomplete_reminders(
		rem_b.title, db_session, principal=_principal(u_a)
	)
	assert not any(str(r.id) == str(rem_b.id) for r in results), (
		"cross-user reminder appeared in pg_trgm autocomplete"
	)


@pytest.mark.asyncio
async def test_reminders_autocomplete_returns_own_reminder(
	db_session: AsyncSession,
) -> None:
	"""user A must find their own reminder via pg_trgm autocomplete."""
	s = _uid()
	u_a = _user(f"ra_own_{s}")
	db_session.add(u_a)
	await db_session.flush()

	list_a = _reminder_list(u_a, f"ra_own_{s}")
	db_session.add(list_a)
	await db_session.flush()

	rem_a = Reminder(
		owner_id=TypeID(u_a.id),
		list_id=list_a.id,
		title=f"my_unique_reminder_{s}",
	)
	db_session.add(rem_a)
	await db_session.commit()

	results = await _autocomplete_reminders(
		rem_a.title, db_session, principal=_principal(u_a)
	)
	ids = [str(r.id) for r in results]
	assert str(rem_a.id) in ids, "user's own reminder not returned by autocomplete"


# ================================================================
# hybrid search - postgres post-filter (defense-in-depth)
# ================================================================


@pytest.mark.asyncio
async def test_notes_hybrid_postgres_postfilter_blocks_cross_user(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""postgres must block user B's note even if the vectorstore returns its ID.

	simulates a hypothetical vector-layer misconfiguration or ACL gap: the
	qdrant result set already contains a note that doesn't belong to the
	querying user. the postgres re-validation step must silently discard it.
	"""
	s = _uid()
	u_a, u_b = _user(f"nh_{s}_a"), _user(f"nh_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	note_b = Note(user_id=str(u_b.id), title=f"leaked_note_{s}", content="private")
	db_session.add(note_b)
	await db_session.commit()

	# make vectorstore return user B's note ID (simulated ACL bypass at vector level)
	monkeypatch.setattr(
		vectorstores_service,
		"search",
		_fake_search_fn(str(note_b.id)),
	)

	results = await notes_service._hybrid_search_notes(
		"leaked", db_session, principal=_principal(u_a), search_params=_SPARSE
	)
	assert not any(str(r.id) == str(note_b.id) for r in results), (
		"postgres post-filter failed to block cross-user note from hybrid search"
	)


@pytest.mark.asyncio
async def test_threads_hybrid_postgres_postfilter_blocks_cross_user(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""postgres must block user B's thread even if the vectorstore returns its ID."""
	s = _uid()
	u_a, u_b = _user(f"th_{s}_a"), _user(f"th_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	thread_b = Thread(
		owner_id=TypeID(u_b.id), title=f"leaked_thread_{s}", is_temporary=False
	)
	db_session.add(thread_b)
	await db_session.commit()

	monkeypatch.setattr(
		vectorstores_service,
		"search",
		_fake_search_fn(str(thread_b.id)),
	)

	results = await _hybrid_search_threads(
		"leaked", db_session, principal=_principal(u_a), search_params=_SPARSE
	)
	assert not any(str(r.id) == str(thread_b.id) for r in results), (
		"postgres post-filter failed to block cross-user thread from hybrid search"
	)


@pytest.mark.asyncio
async def test_reminders_hybrid_postgres_postfilter_blocks_cross_user(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""postgres must block user B's reminder even if the vectorstore returns its ID."""
	s = _uid()
	u_a, u_b = _user(f"rh_{s}_a"), _user(f"rh_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	list_b = _reminder_list(u_b, f"rh_{s}_b")
	db_session.add(list_b)
	await db_session.flush()

	rem_b = Reminder(
		owner_id=TypeID(u_b.id),
		list_id=list_b.id,
		title=f"leaked_reminder_{s}",
	)
	db_session.add(rem_b)
	await db_session.commit()

	monkeypatch.setattr(
		vectorstores_service,
		"search",
		_fake_search_fn(str(rem_b.id)),
	)

	results = await _hybrid_search_reminders(
		"leaked", db_session, principal=_principal(u_a), search_params=_SPARSE
	)
	assert not any(str(r.id) == str(rem_b.id) for r in results), (
		"postgres post-filter failed to block cross-user reminder from hybrid search"
	)


@pytest.mark.asyncio
async def test_hybrid_own_resource_returned_when_vectorstore_matches(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""user's own note is returned when vectorstore correctly reports it."""
	s = _uid()
	u = _user(f"nh_own_{s}")
	db_session.add(u)
	await db_session.flush()

	note = Note(user_id=str(u.id), title=f"my_vector_note_{s}", content="mine")
	db_session.add(note)
	await db_session.commit()

	monkeypatch.setattr(
		vectorstores_service,
		"search",
		_fake_search_fn(str(note.id)),
	)

	results = await notes_service._hybrid_search_notes(
		"mine", db_session, principal=_principal(u), search_params=_SPARSE
	)
	ids = [str(r.id) for r in results]
	assert str(note.id) in ids, (
		"user's own note was unexpectedly blocked by post-filter"
	)


@pytest.mark.asyncio
async def test_threads_hybrid_grantee_can_see_shared_thread(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""user with an explicit access rule can retrieve a thread via hybrid search."""
	s = _uid()
	u_a, u_b = _user(f"th_sh_{s}_a"), _user(f"th_sh_{s}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()

	thread_a = Thread(
		owner_id=TypeID(u_a.id),
		title=f"granted_thread_{s}",
		is_temporary=False,
	)
	db_session.add(thread_a)
	await db_session.flush()

	rule = AccessRule(
		thread_id=str(thread_a.id),
		subject_user_id=TypeID(u_b.id),
		level=AccessLevel.READER,
	)
	db_session.add(rule)
	await db_session.commit()

	monkeypatch.setattr(
		vectorstores_service,
		"search",
		_fake_search_fn(str(thread_a.id)),
	)

	results = await _hybrid_search_threads(
		"granted", db_session, principal=_principal(u_b), search_params=_SPARSE
	)
	ids = [str(r.id) for r in results]
	assert str(thread_a.id) in ids, (
		"grantee could not see explicitly shared thread via hybrid search"
	)
