"""Tests for event service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import EventScope
from api.models.notification import Notification
from api.models.user import User
from api.schemas.event import EventCreate
from api.v1.service import events as event_service


@pytest.mark.asyncio
async def test_emit_event(db_session: AsyncSession) -> None:
	"""Test emitting an event."""
	# Create user
	user = User(
		email="event@example.com",
		username="event",
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
		username="list_event",
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
			scope_id="system",
			type="test.event.2",
			data={},
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
