"""bulk ACL metadata coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.calendar import Calendar, CalendarEvent
from api.models.group import Group
from api.models.message import UserMessage
from api.models.reminder import Reminder, ReminderList
from api.models.role import Role
from api.models.thread import Thread
from api.permissions import ResourceType
from api.tests.factories import create_user
from api.v1.service.authorization import fetch_bulk_acl_metadata
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
@pytest.mark.parametrize(
	"resource_type",
	[ResourceType.MESSAGE, ResourceType.REMINDER, ResourceType.CALENDAR_EVENT],
)
async def test_leaf_metadata_inherits_parent_principals(
	db_session: AsyncSession,
	resource_type: ResourceType,
) -> None:
	owner = await create_user(db_session, f"mo_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"mv_{uuid4().hex[:12]}")
	if resource_type == ResourceType.MESSAGE:
		parent = Thread(owner_id=owner.id, title="metadata thread")
		db_session.add(parent)
		await db_session.flush()
		leaf = UserMessage(thread_id=parent.id, sender_user_id=owner.id)
		rule = AccessRule(
			thread_id=parent.id,
			subject_user_id=viewer.id,
			level=AccessLevel.READER,
		)
	elif resource_type == ResourceType.REMINDER:
		parent = ReminderList(owner_id=owner.id, name=f"metadata {uuid4().hex}")
		db_session.add(parent)
		await db_session.flush()
		leaf = Reminder(owner_id=owner.id, list_id=parent.id, title="metadata reminder")
		rule = AccessRule(
			reminder_list_id=parent.id,
			subject_user_id=viewer.id,
			level=AccessLevel.READER,
		)
	else:
		parent = Calendar(owner_id=owner.id, name=f"metadata {uuid4().hex}")
		db_session.add(parent)
		await db_session.flush()
		start_at = datetime(2026, 8, 10, 9, tzinfo=UTC)
		leaf = CalendarEvent(
			owner_id=owner.id,
			calendar_id=parent.id,
			title="metadata event",
			start_at=start_at,
			end_at=start_at + timedelta(hours=1),
		)
		rule = AccessRule(
			calendar_id=parent.id,
			subject_user_id=viewer.id,
			level=AccessLevel.READER,
		)
	db_session.add_all([leaf, rule])
	await db_session.flush()

	metadata = await fetch_bulk_acl_metadata(
		[str(leaf.id)],
		resource_type,
		db_session,
	)

	assert set(metadata[str(leaf.id)]["allowed_user_ids"]) == {
		str(owner.id),
		str(viewer.id),
	}
	assert metadata[str(leaf.id)]["allowed_group_ids"] == []
	assert metadata[str(leaf.id)]["allowed_role_ids"] == []


@pytest.mark.asyncio
async def test_acl_metadata_returns_user_group_and_role_ids(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"mao_{uuid4().hex[:12]}")
	viewer = await create_user(db_session, f"mav_{uuid4().hex[:12]}")
	group = Group(
		name=f"metadata group {uuid4().hex}",
		description=None,
		owner_id=owner.id,
	)
	role = Role(name=f"metadata-role-{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="metadata ACL resource")
	db_session.add_all([group, role, thread])
	await db_session.flush()
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=viewer.id,
				level=AccessLevel.READER,
			),
			AccessRule(
				thread_id=thread.id,
				subject_group_id=group.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_role_id=role.id,
				level=AccessLevel.ADMIN,
			),
		]
	)
	await db_session.flush()

	metadata = await fetch_bulk_acl_metadata(
		[str(thread.id)],
		ResourceType.THREAD,
		db_session,
	)

	assert metadata[str(thread.id)] == {
		"allowed_user_ids": [str(viewer.id)],
		"allowed_group_ids": [str(group.id)],
		"allowed_role_ids": [str(role.id)],
		"acl_revision": 0,
	}


@pytest.mark.asyncio
async def test_subjectless_rule_is_absent_from_acl_metadata(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"map_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="public ACL metadata")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.flush()

	metadata = await fetch_bulk_acl_metadata(
		[str(thread.id)], ResourceType.THREAD, db_session
	)
	assert metadata[str(thread.id)] == {
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
		"acl_revision": 0,
	}


@pytest.mark.asyncio
async def test_bulk_acl_metadata_empty_input_and_unknown_id(
	db_session: AsyncSession,
) -> None:
	assert await fetch_bulk_acl_metadata([], ResourceType.THREAD, db_session) == {}
	unknown_id = str(new_typeid("thread"))
	assert await fetch_bulk_acl_metadata(
		[unknown_id],
		ResourceType.THREAD,
		db_session,
	) == {
		unknown_id: {
			"allowed_user_ids": [],
			"allowed_group_ids": [],
			"allowed_role_ids": [],
			"acl_revision": 0,
		}
	}
