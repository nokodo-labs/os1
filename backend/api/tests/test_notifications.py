"""Tests for notification service and endpoints."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.notification import Notification
from api.schemas.user import UserCreate
from api.v1.service import notifications as notification_service
from api.v1.service import users as user_service


@pytest.fixture
async def notification_fixture(db_session: AsyncSession):
	"""Create a user, event, and notification."""
	# Create user
	user_in = UserCreate(
		email="notif_test@example.com",
		username="notif_test",
		password="password123",
	)
	user = await user_service.create_user(user_in, db_session)

	# Create event
	event = Event(
		scope=EventScope.USER,
		type="test_event",
		data={"foo": "bar"},
	)
	db_session.add(event)
	await db_session.commit()
	await db_session.refresh(event)

	# Create notification
	notification = Notification(
		user_id=user.id,
		event_id=event.id,
	)
	db_session.add(notification)
	await db_session.commit()
	await db_session.refresh(notification)

	return {"user": user, "event": event, "notification": notification}


@pytest.mark.asyncio
async def test_list_user_notifications(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test listing notifications."""
	user = notification_fixture["user"]
	notifications = await notification_service.list_user_notifications(
		db_session, user_id=user.id
	)
	assert len(notifications) == 1
	assert notifications[0].id == notification_fixture["notification"].id


@pytest.mark.asyncio
async def test_mark_notification_read(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test marking notification as read."""
	notification = notification_fixture["notification"]
	assert notification.read_at is None

	updated = await notification_service.mark_notification_read(
		notification.id, db_session
	)
	assert updated.read_at is not None


@pytest.mark.asyncio
async def test_dismiss_notification(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test dismissing notification."""
	notification = notification_fixture["notification"]
	assert notification.dismissed is False

	updated = await notification_service.dismiss_notification(
		notification.id, db_session
	)
	assert updated.dismissed is True
	# Dismissing should also mark as read if not already
	assert updated.read_at is not None


@pytest.mark.asyncio
async def test_list_unread_notifications(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test listing only unread notifications."""
	user = notification_fixture["user"]
	notification = notification_fixture["notification"]

	# Should be in list
	notifications = await notification_service.list_user_notifications(
		db_session, user_id=user.id, only_unread=True
	)
	assert len(notifications) == 1

	# Mark as read
	await notification_service.mark_notification_read(notification.id, db_session)

	# Should NOT be in list
	notifications = await notification_service.list_user_notifications(
		db_session, user_id=user.id, only_unread=True
	)
	assert len(notifications) == 0


@pytest.mark.asyncio
async def test_get_notification_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent notification."""
	with pytest.raises(HTTPException) as exc:
		await notification_service.mark_notification_read("nonexistent", db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_dismiss_notification_endpoint(
	client: AsyncClient, db_session: AsyncSession, notification_fixture
) -> None:
	"""Ensure POST /v1/notifications/{id}/dismiss toggles the state."""
	notification = notification_fixture["notification"]
	resp = await client.post(f"/v1/notifications/{notification.id}/dismiss")
	assert resp.status_code == 200
	assert resp.json()["dismissed"] is True
