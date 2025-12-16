"""Tests for event service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import EventScope
from api.models.notification import Notification
from api.models.task import Task, TaskType
from api.models.thread import Thread
from api.models.user import User
from api.schemas.event import EventCreate
from api.v1.service import events as event_service


@pytest.mark.asyncio
async def test_emit_event(db_session: AsyncSession) -> None:
	"""Test emitting an event."""
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
		type="test.event",
		data={"foo": "bar"},
		user_id=user.id,
	)
	event = await event_service.emit_event(event_in, db_session)
	assert event.type == "test.event"
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
async def test_list_events(db_session: AsyncSession) -> None:
	"""Test listing events."""
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
	)
	event2 = await event_service.emit_event(
		EventCreate(
			scope=EventScope.SYSTEM,
			scope_id=None,
			type="test.event.2",
			data={},
		),
		db_session,
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
	)

	# List all
	events = await event_service.list_events(db_session)
	assert len(events) >= 2
	ids = {e.id for e in events}
	assert event1.id in ids
	assert event2.id in ids

	# Filter by user
	user_events = await event_service.list_events(db_session, user_id=user.id)
	assert len(user_events) == 1
	assert user_events[0].id == event1.id

	# Filter by scope
	sys_events = await event_service.list_events(db_session, scope=EventScope.SYSTEM)
	assert len(sys_events) >= 1
	assert event2.id in {e.id for e in sys_events}

	# Filter by since
	future_events = await event_service.list_events(
		db_session, since=datetime.now() + timedelta(hours=1)
	)
	assert len(future_events) == 0

	# Filter by thread_id
	thread_events = await event_service.list_events(
		db_session, thread_id=str(thread.id)
	)
	assert len(thread_events) == 1
	assert thread_events[0].id == event3.id

	# Filter by task_id
	task_events = await event_service.list_events(db_session, task_id=str(task.id))
	assert len(task_events) == 1
	assert task_events[0].id == event4.id


@pytest.mark.asyncio
async def test_events_router_endpoints(client: AsyncClient) -> None:
	"""Ensure the events router surfaces emitted events via HTTP."""
	event_payload = {
		"scope": "system",
		"type": "router.test",
		"data": {"ok": True},
	}
	create_resp = await client.post("/v1/events", json=event_payload)
	assert create_resp.status_code == 201
	event_id = create_resp.json()["id"]

	list_resp = await client.get("/v1/events")
	assert list_resp.status_code == 200
	assert any(item["id"] == event_id for item in list_resp.json())
