"""leaf resource authorization coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.calendar import Calendar, CalendarEvent
from api.models.message import MessageType, UserMessage
from api.models.reminder import Reminder, ReminderList
from api.models.thread import Thread
from api.permissions import ResourceType
from api.tests.factories import create_user, principal_for
from api.v1.service.authorization import get_effective_access_level


async def _leaf_resource(
	session: AsyncSession,
	resource_type: ResourceType,
	owner_id: str,
) -> tuple[ReminderList | Calendar, Reminder | CalendarEvent]:
	if resource_type == ResourceType.REMINDER:
		parent = ReminderList(
			owner_id=owner_id,
			name=f"leaf reminders {uuid4().hex}",
		)
		session.add(parent)
		await session.flush()
		leaf = Reminder(
			owner_id=owner_id,
			list_id=parent.id,
			title="leaf reminder",
		)
	else:
		parent = Calendar(
			owner_id=owner_id,
			name=f"leaf calendar {uuid4().hex}",
		)
		session.add(parent)
		await session.flush()
		start_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
		leaf = CalendarEvent(
			owner_id=owner_id,
			calendar_id=parent.id,
			title="leaf event",
			start_at=start_at,
			end_at=start_at + timedelta(hours=1),
		)
	session.add(leaf)
	await session.flush()
	return parent, leaf


def _parent_rule(
	parent: ReminderList | Calendar,
	user_id: str,
	level: AccessLevel,
) -> AccessRule:
	if isinstance(parent, ReminderList):
		return AccessRule(
			reminder_list_id=parent.id,
			subject_user_id=user_id,
			level=level,
		)
	return AccessRule(
		calendar_id=parent.id,
		subject_user_id=user_id,
		level=level,
	)


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"resource_type", [ResourceType.REMINDER, ResourceType.CALENDAR_EVENT]
)
@pytest.mark.parametrize(
	"parent_level",
	[AccessLevel.READER, AccessLevel.EDITOR, AccessLevel.ADMIN],
)
async def test_passthrough_leaf_inherits_exact_parent_level(
	db_session: AsyncSession,
	resource_type: ResourceType,
	parent_level: AccessLevel,
) -> None:
	owner = await create_user(db_session, f"lo_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"lv_{uuid4().hex[:12]}")
	parent, leaf = await _leaf_resource(db_session, resource_type, owner.id)
	db_session.add(_parent_rule(parent, viewer.id, parent_level))
	await db_session.flush()

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(viewer),
			resource_type,
			leaf.id,
		)
		== parent_level
	)


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"resource_type", [ResourceType.REMINDER, ResourceType.CALENDAR_EVENT]
)
async def test_passthrough_leaf_without_parent_access_is_inaccessible(
	db_session: AsyncSession,
	resource_type: ResourceType,
) -> None:
	owner = await create_user(db_session, f"lno_{uuid4().hex[:12]}")
	outsider = await create_user(db_session, f"lnx_{uuid4().hex[:12]}")
	_parent, leaf = await _leaf_resource(db_session, resource_type, owner.id)

	assert (
		await get_effective_access_level(
			db_session,
			principal_for(outsider),
			resource_type,
			leaf.id,
		)
		is None
	)


@pytest.mark.asyncio
async def test_moving_reminder_changes_effective_access(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"mro_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"mrv_{uuid4().hex[:12]}")
	first_list = ReminderList(owner_id=owner.id, name=f"first {uuid4().hex}")
	second_list = ReminderList(owner_id=owner.id, name=f"second {uuid4().hex}")
	db_session.add_all([first_list, second_list])
	await db_session.flush()
	reminder = Reminder(
		owner_id=owner.id,
		list_id=first_list.id,
		title="moving reminder",
	)
	db_session.add(reminder)
	db_session.add_all(
		[
			AccessRule(
				reminder_list_id=first_list.id,
				subject_user_id=viewer.id,
				level=AccessLevel.READER,
			),
			AccessRule(
				reminder_list_id=second_list.id,
				subject_user_id=viewer.id,
				level=AccessLevel.ADMIN,
			),
		]
	)
	await db_session.flush()
	principal = principal_for(viewer)
	assert (
		await get_effective_access_level(
			db_session,
			principal,
			ResourceType.REMINDER,
			reminder.id,
		)
		== AccessLevel.READER
	)

	reminder.list_id = second_list.id
	await db_session.flush()

	assert (
		await get_effective_access_level(
			db_session,
			principal,
			ResourceType.REMINDER,
			reminder.id,
		)
		== AccessLevel.ADMIN
	)


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"resource_type", [ResourceType.REMINDER, ResourceType.CALENDAR_EVENT]
)
async def test_deleting_parent_revokes_leaf_access(
	db_session: AsyncSession,
	resource_type: ResourceType,
) -> None:
	owner = await create_user(db_session, f"dlo_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"dlv_{uuid4().hex[:12]}")
	parent, leaf = await _leaf_resource(db_session, resource_type, owner.id)
	db_session.add(_parent_rule(parent, viewer.id, AccessLevel.EDITOR))
	await db_session.flush()
	principal = principal_for(viewer)
	leaf_id = leaf.id
	assert (
		await get_effective_access_level(
			db_session,
			principal,
			resource_type,
			leaf_id,
		)
		== AccessLevel.EDITOR
	)

	await db_session.delete(parent)
	await db_session.flush()

	assert (
		await get_effective_access_level(
			db_session,
			principal,
			resource_type,
			leaf_id,
		)
		is None
	)


@pytest.mark.asyncio
async def test_authored_and_passthrough_leaf_resolution_return_exact_levels(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"lpo_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"lpv_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="leaf path parity")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=viewer.id,
	)
	db_session.add(message)
	_parent, reminder = await _leaf_resource(
		db_session,
		ResourceType.REMINDER,
		owner.id,
	)
	assert isinstance(_parent, ReminderList)
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=viewer.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				reminder_list_id=_parent.id,
				subject_user_id=viewer.id,
				level=AccessLevel.EDITOR,
			),
		]
	)
	await db_session.flush()
	principal = principal_for(viewer)

	assert (
		await get_effective_access_level(
			db_session,
			principal,
			ResourceType.MESSAGE,
			message.id,
		)
		== AccessLevel.EDITOR
	)
	assert (
		await get_effective_access_level(
			db_session,
			principal,
			ResourceType.REMINDER,
			reminder.id,
		)
		== AccessLevel.EDITOR
	)
