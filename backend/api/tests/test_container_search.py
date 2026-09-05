"""container search: anchored and anchorless reminder-list and calendar results.

covers the unified container search services (search_reminder_lists,
search_calendars): sub-resource hits carry an anchor into the container,
container-name hits are anchorless, empty containers are findable by their
own name, cross-user containers never leak, and aggregator dedupe honors
the per-type anchor fanout.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.calendar import Calendar, CalendarEvent
from api.models.reminder import Reminder, ReminderList
from api.models.user import User
from api.permissions import DefaultResourceAccess
from api.schemas.search import (
	SearchMode,
	SearchParams,
	SearchResourceReferenceType,
	SearchResultAnchor,
	SearchResultItem,
	SearchResultType,
)
from api.v1.service.authentication import Principal
from api.v1.service.calendar.search import (
	calendar_or_event_to_search_item,
	search_calendars,
)
from api.v1.service.reminders.search import (
	reminder_or_list_to_search_item,
	search_reminder_lists,
)
from api.v1.service.search import aggregator
from api.v1.service.search.aggregator import _dedupe_key
from api.v1.service.search.primitives import ScoredResult
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import new_typeid


_AUTOCOMPLETE = SearchParams(mode=SearchMode.AUTOCOMPLETE)


def _uid() -> str:
	return uuid4().hex[:8]


def _user(suffix: str) -> User:
	return User(
		email=f"{suffix}@container.test",
		username=f"cs_{suffix}",
		hashed_password=hash_password("x"),
		is_active=True,
		is_superuser=False,
	)


def _principal(user: User) -> Principal:
	return Principal.for_user(
		user=user,
		group_ids=(),
		permissions=frozenset(),
		role_resource_defaults=DefaultResourceAccess(),
	)


async def _reminder_list_items(
	*args: object, **kwargs: object
) -> list[SearchResultItem]:
	"""search then project, mirroring the aggregator's collect step."""
	scored = await search_reminder_lists(*args, **kwargs)
	return [reminder_or_list_to_search_item(s.item, s.score) for s in scored]


async def _calendar_items(*args: object, **kwargs: object) -> list[SearchResultItem]:
	"""search then project, mirroring the aggregator's collect step."""
	scored = await search_calendars(*args, **kwargs)
	return [calendar_or_event_to_search_item(s.item, s.score) for s in scored]


# reminder lists


@pytest.mark.asyncio
async def test_reminder_list_search_returns_anchored_and_anchorless(
	db_session: AsyncSession,
) -> None:
	"""one query matching a list name and a reminder yields both result shapes."""
	token = f"zq{_uid()}"
	user = _user(f"rl_{token}")
	db_session.add(user)
	await db_session.flush()
	rlist = ReminderList(owner_id=user.id, name=f"errands {token}", color="#22c55e")
	db_session.add(rlist)
	await db_session.flush()
	reminder = Reminder(owner_id=user.id, list_id=rlist.id, title=f"buy milk {token}")
	db_session.add(reminder)
	await db_session.commit()

	items = await _reminder_list_items(
		token,
		db_session,
		principal=_principal(user),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert all(item.type == SearchResultType.REMINDER_LIST for item in items)
	assert all(str(item.id) == str(rlist.id) for item in items)
	anchored = [item for item in items if item.anchor is not None]
	anchorless = [item for item in items if item.anchor is None]
	assert len(anchored) == 1
	anchor = anchored[0].anchor
	assert anchor is not None
	assert anchor.type == SearchResourceReferenceType.REMINDER
	assert str(anchor.id) == str(reminder.id)
	assert anchored[0].title == reminder.title
	assert len(anchorless) == 1
	assert anchorless[0].title == rlist.name
	assert all(item.score is not None for item in items)


@pytest.mark.asyncio
async def test_empty_reminder_list_found_by_own_name(
	db_session: AsyncSession,
) -> None:
	"""a list with zero reminders is findable by its own name, anchorless."""
	token = f"zq{_uid()}"
	user = _user(f"rle_{token}")
	db_session.add(user)
	await db_session.flush()
	rlist = ReminderList(owner_id=user.id, name=f"someday {token}", color="#22c55e")
	db_session.add(rlist)
	await db_session.commit()

	items = await _reminder_list_items(
		token,
		db_session,
		principal=_principal(user),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert len(items) == 1
	assert str(items[0].id) == str(rlist.id)
	assert items[0].anchor is None
	assert items[0].title == rlist.name


@pytest.mark.asyncio
async def test_reminder_list_name_search_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	"""user A must not find user B's list via the container-name tier."""
	token = f"zq{_uid()}"
	u_a, u_b = _user(f"rli_{token}_a"), _user(f"rli_{token}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()
	list_b = ReminderList(owner_id=u_b.id, name=f"private {token}", color="#22c55e")
	db_session.add(list_b)
	await db_session.commit()

	items = await _reminder_list_items(
		token,
		db_session,
		principal=_principal(u_a),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert not items


# calendars


@pytest.mark.asyncio
async def test_calendar_search_returns_anchored_and_anchorless(
	db_session: AsyncSession,
) -> None:
	"""one query matching a calendar name and an event yields both result shapes."""
	token = f"zq{_uid()}"
	user = _user(f"cal_{token}")
	db_session.add(user)
	await db_session.flush()
	calendar = Calendar(owner_id=user.id, name=f"work {token}")
	db_session.add(calendar)
	await db_session.flush()
	start = datetime.now(tz=UTC)
	event = CalendarEvent(
		owner_id=user.id,
		calendar_id=calendar.id,
		title=f"standup {token}",
		start_at=start,
		end_at=start + timedelta(hours=1),
	)
	db_session.add(event)
	await db_session.commit()

	items = await _calendar_items(
		token,
		db_session,
		principal=_principal(user),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert all(item.type == SearchResultType.CALENDAR for item in items)
	assert all(str(item.id) == str(calendar.id) for item in items)
	anchored = [item for item in items if item.anchor is not None]
	anchorless = [item for item in items if item.anchor is None]
	assert len(anchored) == 1
	anchor = anchored[0].anchor
	assert anchor is not None
	assert anchor.type == SearchResourceReferenceType.CALENDAR_EVENT
	assert str(anchor.id) == str(event.id)
	assert anchored[0].title == event.title
	assert len(anchorless) == 1
	assert anchorless[0].title == calendar.name


@pytest.mark.asyncio
async def test_empty_calendar_found_by_own_name(db_session: AsyncSession) -> None:
	"""a calendar with zero events is findable by its own name, anchorless."""
	token = f"zq{_uid()}"
	user = _user(f"cale_{token}")
	db_session.add(user)
	await db_session.flush()
	calendar = Calendar(owner_id=user.id, name=f"holidays {token}")
	db_session.add(calendar)
	await db_session.commit()

	items = await _calendar_items(
		token,
		db_session,
		principal=_principal(user),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert len(items) == 1
	assert str(items[0].id) == str(calendar.id)
	assert items[0].anchor is None
	assert items[0].title == calendar.name


@pytest.mark.asyncio
async def test_calendar_name_search_isolates_other_user(
	db_session: AsyncSession,
) -> None:
	"""user A must not find user B's calendar via the container-name tier."""
	token = f"zq{_uid()}"
	u_a, u_b = _user(f"cali_{token}_a"), _user(f"cali_{token}_b")
	db_session.add_all([u_a, u_b])
	await db_session.flush()
	cal_b = Calendar(owner_id=u_b.id, name=f"private {token}")
	db_session.add(cal_b)
	await db_session.commit()

	items = await _calendar_items(
		token,
		db_session,
		principal=_principal(u_a),
		limit=10,
		search_params=_AUTOCOMPLETE,
	)

	assert not items


# aggregator anchor fanout


def _item(
	result_type: SearchResultType,
	item_id: str,
	anchor: SearchResultAnchor | None,
) -> SearchResultItem:
	now = datetime.now(tz=UTC)
	return SearchResultItem(
		type=result_type,
		id=item_id,
		title="t",
		anchor=anchor,
		created_at=now,
		updated_at=now,
	)


def test_dedupe_key_fans_out_reminder_list_anchors() -> None:
	"""ALL fanout: same container with distinct anchors yields distinct keys."""
	list_id = str(new_typeid("remlst"))
	a1 = SearchResultAnchor(
		type=SearchResourceReferenceType.REMINDER, id=new_typeid("rem")
	)
	a2 = SearchResultAnchor(
		type=SearchResourceReferenceType.REMINDER, id=new_typeid("rem")
	)
	key1 = _dedupe_key(_item(SearchResultType.REMINDER_LIST, list_id, a1))
	key2 = _dedupe_key(_item(SearchResultType.REMINDER_LIST, list_id, a2))
	keyless = _dedupe_key(_item(SearchResultType.REMINDER_LIST, list_id, None))
	assert key1 != key2
	assert keyless == list_id
	assert key1 != keyless


def test_dedupe_key_collapses_thread_anchors() -> None:
	"""BEST fanout: thread items share one key regardless of anchor."""
	thread_id = str(new_typeid("thread"))
	a1 = SearchResultAnchor(
		type=SearchResourceReferenceType.MESSAGE, id=new_typeid("msg")
	)
	a2 = SearchResultAnchor(
		type=SearchResourceReferenceType.MESSAGE, id=new_typeid("msg")
	)
	key1 = _dedupe_key(_item(SearchResultType.THREAD, thread_id, a1))
	key2 = _dedupe_key(_item(SearchResultType.THREAD, thread_id, a2))
	assert key1 == key2 == thread_id


# search_stream ordering


def _scored(item_id: str, score: float) -> ScoredResult[_Row]:
	return ScoredResult(item=_Row(item_id), score=score)


@dataclass(frozen=True)
class _Row:
	"""minimal stand-in for a hydrated resource row."""

	id: str


def _row_to_item(row: _Row, score: float | None) -> SearchResultItem:
	now = datetime.now(tz=UTC)
	return SearchResultItem(
		type=SearchResultType.NOTE,
		id=row.id,
		title=row.id,
		score=score,
		created_at=now,
		updated_at=now,
	)


@pytest.mark.asyncio
async def test_search_stream_orders_by_score_not_completion(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""results are score-ordered even when a weaker tier resolves first.

	the tiers are gathered concurrently, so completion order is not a
	meaningful ranking signal; sorting must happen before results are yielded.
	"""
	note_id = str(new_typeid("note"))
	thread_id = str(new_typeid("thread"))

	async def _weak_note_tier(*args: object, **kwargs: object):
		# resolves immediately, but scores worse than the thread tier.
		return [_scored(note_id, 0.10)]

	async def _strong_thread_tier(*args: object, **kwargs: object):
		# resolves last, yet must be ranked first.
		await asyncio.sleep(0.02)
		return [_scored(thread_id, 0.99)]

	monkeypatch.setattr(aggregator, "search_notes", _weak_note_tier)
	monkeypatch.setattr(aggregator, "note_to_search_item", _row_to_item)
	monkeypatch.setattr(aggregator, "search_threads", _strong_thread_tier)
	monkeypatch.setattr(aggregator, "thread_to_search_item", _row_to_item)
	user = _user(_uid())
	db_session.add(user)
	await db_session.flush()

	items = [
		item
		async for item in aggregator.search_stream(
			"q",
			db_session,
			principal=_principal(user),
			types=[SearchResultType.NOTE, SearchResultType.THREAD],
			limit=10,
			search_params=_AUTOCOMPLETE,
		)
	]

	assert [item.id for item in items] == [thread_id, note_id]


@pytest.mark.asyncio
async def test_search_stream_dedupe_keeps_best_scored_copy(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""when two tiers return the same container, the better score survives.

	dedupe keeps the first copy it sees, so it is only correct if sorting
	already happened - otherwise the winner is whichever tier finished first.
	"""
	shared_id = str(new_typeid("note"))

	async def _weak_tier(*args: object, **kwargs: object):
		return [_scored(shared_id, 0.10)]

	async def _strong_tier(*args: object, **kwargs: object):
		await asyncio.sleep(0.02)
		return [_scored(shared_id, 0.99)]

	monkeypatch.setattr(aggregator, "search_notes", _weak_tier)
	monkeypatch.setattr(aggregator, "note_to_search_item", _row_to_item)
	monkeypatch.setattr(aggregator, "search_threads", _strong_tier)
	monkeypatch.setattr(aggregator, "thread_to_search_item", _row_to_item)
	user = _user(_uid())
	db_session.add(user)
	await db_session.flush()

	items = [
		item
		async for item in aggregator.search_stream(
			"q",
			db_session,
			principal=_principal(user),
			types=[SearchResultType.NOTE, SearchResultType.THREAD],
			limit=10,
			search_params=_AUTOCOMPLETE,
		)
	]

	assert len(items) == 1
	assert items[0].score == 0.99
