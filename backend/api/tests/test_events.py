"""Tests for event service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.task import Task, TaskType
from api.models.thread import Thread
from api.models.user import User
from api.schemas.event import EventCreate
from api.v1.service import events as event_service
from api.v1.service.auth import Principal


def _admin_principal() -> Principal:
	user = User(
		email="admin@example.com",
		hashed_password="x",
		is_active=True,
		is_superuser=True,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	return Principal(user=user, group_ids=(), permissions=frozenset())


def _non_admin_events_manager_principal(user: User) -> Principal:
	return Principal(
		user=user,
		group_ids=(),
		permissions=frozenset({"events:manage"}),
	)


@pytest.mark.asyncio
async def test_emit_event(db_session: AsyncSession) -> None:
	"""Test emitting an event."""
	principal = _admin_principal()
	# Create user
	user = User(
		email="event@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(user)
	await db_session.commit()
	await db_session.refresh(user)

	event_in = EventCreate(
		scope=EventScope.USER,
		scope_id=str(user.id),
		type=EventType.NOTIFICATION_CUSTOM,
		data={"foo": "bar"},
		user_id=user.id,
	)
	event = await event_service.emit_event(event_in, db_session, principal=principal)
	assert event.type == EventType.NOTIFICATION_CUSTOM
	assert event.user_id == user.id
	assert event.data == {"foo": "bar"}

	# Check notification created
	result = await db_session.execute(
		select(Notification).where(Notification.event_id == event.id)
	)
	notification = result.scalar_one_or_none()
	assert notification is not None
	assert notification.user_id == user.id


@pytest.mark.asyncio
async def test_emit_event_non_admin_cannot_notify_other_user(
	db_session: AsyncSession,
) -> None:
	"""Non-admins may only create notifications for themselves."""
	actor = User(
		email="actor@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	target = User(
		email="target@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add_all([actor, target])
	await db_session.commit()
	await db_session.refresh(actor)
	await db_session.refresh(target)

	principal = _non_admin_events_manager_principal(actor)

	with pytest.raises(Exception) as excinfo:
		await event_service.emit_event(
			EventCreate(
				scope=EventScope.USER,
				scope_id=str(target.id),
				type=EventType.NOTIFICATION_CUSTOM,
				data={"foo": "bar"},
				user_id=target.id,
			),
			db_session,
			principal=principal,
		)

	# Avoid importing FastAPI HTTPException directly in tests; assert via status_code.
	err = excinfo.value
	assert getattr(err, "status_code", None) == 403


@pytest.mark.asyncio
async def test_list_events(db_session: AsyncSession) -> None:
	"""Test listing events."""
	principal = _admin_principal()
	# Create user
	user = User(
		email="list_event@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(user)
	await db_session.commit()
	await db_session.refresh(user)

	# Emit events
	event1 = await event_service.emit_event(
		EventCreate(
			scope=EventScope.USER,
			scope_id=str(user.id),
			type="test.event.1",
			data={},
			user_id=user.id,
		),
		db_session,
		principal=principal,
	)
	event2 = await event_service.emit_event(
		EventCreate(
			scope=EventScope.SYSTEM,
			scope_id=None,
			type="test.event.2",
			data={},
		),
		db_session,
		principal=principal,
	)

	# Emit event with thread_id
	thread = Thread(owner_id=user.id, title="test thread")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)

	event3 = await event_service.emit_event(
		EventCreate(
			scope=EventScope.THREAD,
			scope_id=str(thread.id),
			type="test.event.3",
			data={},
			thread_id=str(thread.id),
		),
		db_session,
		principal=principal,
	)

	# Emit event with task_id
	task = Task(user_id=user.id, task_type=TaskType.CUSTOM)
	db_session.add(task)
	await db_session.commit()
	await db_session.refresh(task)

	event4 = await event_service.emit_event(
		EventCreate(
			scope=EventScope.TASK,
			scope_id=str(task.id),
			type="test.event.4",
			data={},
			task_id=str(task.id),
		),
		db_session,
		principal=principal,
	)

	# List all
	events = await event_service.list_events(db_session, principal=principal)
	assert len(events) >= 2
	ids = {e.id for e in events}
	assert event1.id in ids
	assert event2.id in ids

	# Filter by user
	user_events = await event_service.list_events(
		db_session,
		user_id=user.id,
		principal=principal,
	)
	assert len(user_events) == 1
	assert user_events[0].id == event1.id

	# Filter by scope
	sys_events = await event_service.list_events(
		db_session,
		scope=EventScope.SYSTEM,
		principal=principal,
	)
	assert len(sys_events) >= 1
	assert event2.id in {e.id for e in sys_events}

	# Filter by since
	future_events = await event_service.list_events(
		db_session,
		since=datetime.now() + timedelta(hours=1),
		principal=principal,
	)
	assert len(future_events) == 0

	# Filter by thread_id
	thread_events = await event_service.list_events(
		db_session,
		thread_id=str(thread.id),
		principal=principal,
	)
	assert len(thread_events) == 1
	assert thread_events[0].id == event3.id

	# Filter by task_id
	task_events = await event_service.list_events(
		db_session,
		task_id=str(task.id),
		principal=principal,
	)
	assert len(task_events) == 1
	assert task_events[0].id == event4.id


@pytest.mark.asyncio
async def test_events_router_endpoints(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Ensure the events router surfaces emitted events via HTTP."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	event_payload = {
		"scope": "system",
		"type": "router.test",
		"data": {"ok": True},
	}
	create_resp = await client.post("/v1/events", json=event_payload, headers=headers)
	assert create_resp.status_code == 201
	event_id = create_resp.json()["id"]

	list_resp = await client.get("/v1/events", headers=headers)
	assert list_resp.status_code == 200
	assert any(item["id"] == event_id for item in list_resp.json())
