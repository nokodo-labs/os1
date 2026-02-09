"""Tests for notification service and endpoints."""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.notification import Notification
from api.models.thread import Thread
from api.schemas.user import UserCreate
from api.v1.service import notifications as notification_service
from api.v1.service import threads as thread_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest_asyncio.fixture
async def notification_fixture(db_session: AsyncSession):
	"""Create a user, event, and notification."""
	# Create user
	user_in = UserCreate(
		email="notif_test@example.com",
		password="password123",
		is_superuser=True,
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	notifications = await notification_service.list_user_notifications(
		db_session,
		user_id=user.id,
		principal=principal,
	)
	assert len(notifications) == 1
	assert notifications[0].id == notification_fixture["notification"].id


@pytest.mark.asyncio
async def test_mark_notification_read(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test marking notification as read."""
	notification = notification_fixture["notification"]
	user = notification_fixture["user"]
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	assert notification.read_at is None

	updated = await notification_service.mark_notification_read(
		notification.id,
		db_session,
		principal=principal,
	)
	assert updated.read_at is not None


@pytest.mark.asyncio
async def test_dismiss_notification(
	db_session: AsyncSession, notification_fixture
) -> None:
	"""Test dismissing notification."""
	notification = notification_fixture["notification"]
	user = notification_fixture["user"]
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	assert notification.dismissed is False

	updated = await notification_service.dismiss_notification(
		notification.id,
		db_session,
		principal=principal,
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	# Should be in list
	notifications = await notification_service.list_user_notifications(
		db_session,
		user_id=user.id,
		only_unread=True,
		principal=principal,
	)
	assert len(notifications) == 1

	# Mark as read
	await notification_service.mark_notification_read(
		notification.id,
		db_session,
		principal=principal,
	)

	# Should NOT be in list
	notifications = await notification_service.list_user_notifications(
		db_session,
		user_id=user.id,
		only_unread=True,
		principal=principal,
	)
	assert len(notifications) == 0


@pytest.mark.asyncio
async def test_get_notification_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent notification."""
	user = await user_service.create_user(
		UserCreate(
			email="notif_nf@example.com", password="password123", is_superuser=True
		),
		db_session,
	)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException) as exc:
		await notification_service.mark_notification_read(
			"nonexistent",
			db_session,
			principal=principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_notification_access_guard(db_session: AsyncSession) -> None:
	"""Ensure users cannot mark others' notifications."""
	admin = await user_service.create_user(
		UserCreate(
			email="notif_guard_admin@example.com", password="pw", is_superuser=True
		),
		db_session,
	)
	user_a = await user_service.create_user(
		UserCreate(email="notif_guard_a@example.com", password="pw"),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	user_b = await user_service.create_user(
		UserCreate(email="notif_guard_b@example.com", password="pw"),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	event = Event(scope=EventScope.USER, type="guard", data={}, user_id=user_a.id)
	db_session.add(event)
	await db_session.flush()
	note = Notification(
		id=TypeID(new_typeid("notif")),
		user_id=user_a.id,
		event_id=event.id,
	)
	db_session.add(note)
	await db_session.commit()

	principal_b = Principal(user=user_b, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		await notification_service.mark_notification_read(
			note.id,
			db_session,
			principal=principal_b,
		)


@pytest.mark.asyncio
async def test_dismiss_notification_endpoint(
	client: AsyncClient, db_session: AsyncSession, notification_fixture
) -> None:
	"""Ensure POST /v1/notifications/{id}/dismiss toggles the state."""
	notification = notification_fixture["notification"]
	user = notification_fixture["user"]
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	resp = await client.post(
		f"/v1/notifications/{notification.id}/dismiss",
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 200
	assert resp.json()["dismissed"] is True


@pytest.mark.asyncio
async def test_list_notifications_forbidden_other_user(
	db_session: AsyncSession,
) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="notif_list_admin@example.com", password="pw", is_superuser=True
		),
		db_session,
	)
	user_a = await user_service.create_user(
		UserCreate(email="notif_list_a@example.com", password="pw"),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	user_b = await user_service.create_user(
		UserCreate(email="notif_list_b@example.com", password="pw"),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	event = Event(scope=EventScope.USER, type="list-guard", data={}, user_id=user_a.id)
	db_session.add(event)
	await db_session.flush()
	note = Notification(user_id=user_a.id, event_id=event.id)
	db_session.add(note)
	await db_session.commit()

	principal_b = Principal(user=user_b, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		await notification_service.list_user_notifications(
			db_session,
			user_id=user_a.id,
			principal=principal_b,
		)


@pytest.mark.asyncio
async def test_send_agent_notification_thread_includes_owner_when_no_participants(
	db_session: AsyncSession,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="thread_owner_notif@example.com", password="pw", is_superuser=True
		),
		db_session,
	)
	thread = Thread(owner_id=owner.id, title="test thread")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)

	principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	user_ids = await thread_service.list_thread_recipient_user_ids(
		TypeID(str(thread.id)),
		db_session,
		principal=principal,
	)

	notifications = await notification_service.send_agent_notification(
		db_session,
		title="hello",
		body="world",
		user_ids=user_ids,
	)
	assert len(notifications) == 1
	assert str(notifications[0].user_id) == str(owner.id)
