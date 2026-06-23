"""Tests for notification service and endpoints."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.notification import NotificationListFilters, NotificationPayload
from api.schemas.user import UserCreate
from api.settings import settings
from api.v1.service import notifications as notification_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import list_accessible_user_ids
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest_asyncio.fixture
async def notification_fixture(db_session: AsyncSession) -> dict[str, Any]:
	"""Create a user, event, and notification."""
	# Create user
	user_in = UserCreate(
		email="notif_test@example.com",
		username="notif_test",
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
		title="test notification",
	)
	db_session.add(notification)
	await db_session.commit()
	await db_session.refresh(notification)

	return {"user": user, "event": event, "notification": notification}


@pytest.mark.asyncio
async def test_list_user_notifications(
	db_session: AsyncSession, notification_fixture: dict[str, Any]
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
async def test_list_user_notifications_omits_expired(
	db_session: AsyncSession, notification_fixture: dict[str, Any]
) -> None:
	"""expired notifications are dropped from normal reads."""
	user = notification_fixture["user"]
	notification = notification_fixture["notification"]
	notification.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
	await db_session.commit()
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	notifications = await notification_service.list_user_notifications(
		db_session,
		user_id=user.id,
		principal=principal,
	)
	assert notifications == []


@pytest.mark.asyncio
async def test_mark_notification_read(
	db_session: AsyncSession, notification_fixture: dict[str, Any]
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
	db_session: AsyncSession, notification_fixture: dict[str, Any]
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
	db_session: AsyncSession, notification_fixture: dict[str, Any]
) -> None:
	"""Test listing only unread notifications."""
	user = notification_fixture["user"]
	notification = notification_fixture["notification"]
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	# Should be in list
	notifications = await notification_service.list_user_notifications(
		db_session,
		user_id=user.id,
		principal=principal,
		filters=NotificationListFilters(only_unread=True),
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
		principal=principal,
		filters=NotificationListFilters(only_unread=True),
	)
	assert len(notifications) == 0


@pytest.mark.asyncio
async def test_get_notification_not_found(db_session: AsyncSession) -> None:
	"""Test getting a non-existent notification."""
	user = await user_service.create_user(
		UserCreate(
			email="notif_nf@example.com",
			username="notif_nf_test",
			password="password123",
			is_superuser=True,
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
			email="notif_guard_admin@example.com",
			username="notif_guard_admin",
			password="pw",
			is_superuser=True,
		),
		db_session,
	)
	user_a = await user_service.create_user(
		UserCreate(
			email="notif_guard_a@example.com",
			username="notif_guard_a",
			password="pw",
		),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	user_b = await user_service.create_user(
		UserCreate(
			email="notif_guard_b@example.com",
			username="notif_guard_b",
			password="pw",
		),
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
		title="guard notification",
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
	client: AsyncClient, db_session: AsyncSession, notification_fixture: dict[str, Any]
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
async def test_create_notification_accepts_title_only_and_payload_fields(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="notif_contract@example.com",
			username="notif_contract",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	previous_ttl = settings.notifications.notification_ttl_seconds
	settings.notifications.notification_ttl_seconds = 120

	try:
		resp = await client.post(
			"/v1/notifications",
			json={
				"user_ids": [str(user.id)],
				"title": " ship complete ",
				"action_url": " /projects/demo ",
				"tag": " project-demo ",
				"data": {"project_id": "project_demo"},
				"actions": [{"action": " open ", "title": " open ", "icon_url": " "}],
			},
			headers={"Authorization": f"Bearer {token}"},
		)
	finally:
		settings.notifications.notification_ttl_seconds = previous_ttl
	assert resp.status_code == 201
	payload = resp.json()[0]
	assert payload["title"] == "ship complete"
	assert payload["body"] is None
	assert payload["action_url"] == "/projects/demo"
	assert payload["tag"] == "project-demo"
	assert payload["data"] == {"project_id": "project_demo"}
	assert payload["actions"] == [{"action": "open", "title": "open", "icon_url": None}]
	assert payload["expires_at"] is not None
	assert payload["event"]["type"] == "notification.custom"
	assert payload["event"]["data"]["notification_id"] == payload["id"]
	event_payload = payload["event"]["data"]["payload"]
	assert event_payload["id"] == payload["id"]
	assert event_payload["title"] == "ship complete"
	assert event_payload["action_url"] == "/projects/demo"
	assert event_payload["data"] == {
		"project_id": "project_demo",
		"notification_id": payload["id"],
		"action_url": "/projects/demo",
	}
	assert datetime.fromisoformat(
		event_payload["expires_at"]
	) == datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_create_notification_endpoint_requires_admin(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="notif_admin_guard_admin@example.com",
			username="notif_admin_guard_admin",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	user = await user_service.create_user(
		UserCreate(
			email="notif_admin_guard_user@example.com",
			username="notif_admin_guard_user",
			password="password123",
		),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]

	resp = await client.post(
		"/v1/notifications",
		json={"user_ids": [str(user.id)], "title": "manual test"},
		headers={"Authorization": f"Bearer {token}"},
	)
	assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deliver_notification_skips_expired(
	db_session: AsyncSession,
	notification_fixture: dict[str, Any],
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""expired durable notifications are not sent to live or push channels."""
	notification = notification_fixture["notification"]
	notification.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)
	await db_session.commit()
	await db_session.refresh(notification, attribute_names=["event"])
	called = False

	async def fake_fanout(event: Event) -> None:
		nonlocal called
		_ = event
		called = True

	def fake_schedule_push(note: Notification) -> None:
		nonlocal called
		_ = note
		called = True

	monkeypatch.setattr(notification_service, "fanout_event", fake_fanout)
	monkeypatch.setattr(
		notification_service, "schedule_notification_push", fake_schedule_push
	)

	await notification_service.deliver_notification(notification)
	assert called is False


@pytest.mark.asyncio
async def test_push_subscription_register_list_delete_endpoint(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	user = await user_service.create_user(
		UserCreate(
			email="push_sub@example.com",
			username="push_sub",
			password="password123",
			is_superuser=True,
		),
		db_session,
	)
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user.email, "password": "password123"},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}
	client_resp = await client.post(
		f"/v1/users/{user.id}/clients",
		json={
			"client_key": "test-client-key",
			"name": "desktop browser",
			"user_agent": "test browser",
			"info": {"platform": "windows", "browser": "chromium"},
		},
		headers=headers,
	)
	assert client_resp.status_code == 200
	user_client = client_resp.json()

	resp = await client.post(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		json={
			"endpoint": "https://push.example/subscription/1",
			"keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
		},
		headers=headers,
	)
	assert resp.status_code == 201
	created = resp.json()
	assert created["endpoint"] == "https://push.example/subscription/1"
	assert created["client_id"] == user_client["id"]
	assert "user_id" not in created
	assert "p256dh" not in created
	assert "auth" not in created

	list_resp = await client.get(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		headers=headers,
	)
	assert list_resp.status_code == 200
	assert [item["id"] for item in list_resp.json()] == [created["id"]]

	unregister_resp = await client.request(
		"DELETE",
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		json={"endpoint": "https://push.example/subscription/1"},
		headers=headers,
	)
	assert unregister_resp.status_code == 204

	list_after_unregister = await client.get(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		headers=headers,
	)
	assert list_after_unregister.status_code == 200
	assert list_after_unregister.json() == []

	resp = await client.post(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		json={
			"endpoint": "https://push.example/subscription/1",
			"keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
		},
		headers=headers,
	)
	assert resp.status_code == 201
	created = resp.json()

	delete_resp = await client.delete(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions/{created['id']}",
		headers=headers,
	)
	assert delete_resp.status_code == 204

	list_after_delete = await client.get(
		f"/v1/users/{user.id}/clients/{user_client['id']}/push-subscriptions",
		headers=headers,
	)
	assert list_after_delete.status_code == 200
	assert list_after_delete.json() == []


@pytest.mark.asyncio
async def test_list_notifications_forbidden_other_user(
	db_session: AsyncSession,
) -> None:
	admin = await user_service.create_user(
		UserCreate(
			email="notif_list_admin@example.com",
			username="notif_list_admin",
			password="pw",
			is_superuser=True,
		),
		db_session,
	)
	user_a = await user_service.create_user(
		UserCreate(
			email="notif_list_a@example.com",
			username="notif_list_a",
			password="pw",
		),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	user_b = await user_service.create_user(
		UserCreate(
			email="notif_list_b@example.com",
			username="notif_list_b",
			password="pw",
		),
		db_session,
		principal=Principal(user=admin, group_ids=(), permissions=frozenset()),
	)
	event = Event(scope=EventScope.USER, type="list-guard", data={}, user_id=user_a.id)
	db_session.add(event)
	await db_session.flush()
	note = Notification(
		user_id=user_a.id,
		event_id=event.id,
		title="list guard notification",
	)
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
async def test_create_agent_notification_thread_includes_owner_when_no_participants(
	db_session: AsyncSession,
) -> None:
	owner = await user_service.create_user(
		UserCreate(
			email="thread_owner_notif@example.com",
			username="thread_owner_notif",
			password="pw",
			is_superuser=True,
		),
		db_session,
	)
	thread = Thread(owner_id=owner.id, title="test thread")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)

	user_ids = await list_accessible_user_ids(
		ResourceType.THREAD,
		thread.id,
		db_session,
	)

	notifications = await notification_service.create_notifications(
		db_session,
		payload=NotificationPayload(
			title="hello",
			body="world",
			icon_url="/icon.png",
		),
		event_type=EventType.NOTIFICATION_AGENT,
		user_ids=user_ids,
	)
	assert len(notifications) == 1
	assert str(notifications[0].user_id) == str(owner.id)
	assert notifications[0].title == "hello"
	assert notifications[0].body == "world"
	assert notifications[0].icon_url == "/icon.png"
	event_payload = notifications[0].event.data["payload"]
	assert event_payload["title"] == "hello"
	assert event_payload["icon_url"] == "/icon.png"
