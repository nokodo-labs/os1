"""Tests for event service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessRule
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.notification import Notification
from api.models.task import Task, TaskType
from api.models.thread import Thread
from api.models.user import User
from api.permissions import AccessLevel, ResourceType
from api.schemas.event import EventCreate, EventListFilters
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.chat import run_status
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _admin_principal() -> Principal:
	user = User(
		email="admin@example.com",
		username="admin_events",
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
async def test_create_event_from_request(db_session: AsyncSession) -> None:
	"""Test creating an event from an API request."""
	principal = _admin_principal()
	# Create user
	user = User(
		email="event@example.com",
		username="event_test",
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
		scope_id=user.id,
		type=EventType.NOTIFICATION_CUSTOM,
		data={"foo": "bar"},
		user_id=user.id,
	)
	event = await event_service.create_event_from_request(
		event_in,
		db_session,
		principal=principal,
	)
	assert event.type == EventType.NOTIFICATION_CUSTOM
	assert event.user_id == user.id
	assert event.data == {"foo": "bar"}

	# event creation does not auto-create notifications (use notifications.py)
	result = await db_session.execute(
		select(Notification).where(Notification.event_id == event.id)
	)
	notification = result.scalar_one_or_none()
	assert notification is None  # clean architecture: events != notifications


@pytest.mark.asyncio
async def test_create_event_from_request_non_admin_cannot_notify_other_user(
	db_session: AsyncSession,
) -> None:
	"""Non-admins may only create notifications for themselves."""
	actor = User(
		email="actor@example.com",
		username="actor_test",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	target = User(
		email="target@example.com",
		username="target_test",
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
		await event_service.create_event_from_request(
			EventCreate(
				scope=EventScope.USER,
				scope_id=target.id,
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
async def test_create_event_from_request_non_admin_cannot_target_other_user_scope(
	db_session: AsyncSession,
) -> None:
	"""Non-admins cannot route user-scoped events to another user."""
	actor = User(
		email="scope_actor@example.com",
		username="scope_actor_test",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	target = User(
		email="scope_target@example.com",
		username="scope_target_test",
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
		await event_service.create_event_from_request(
			EventCreate(
				scope=EventScope.USER,
				scope_id=target.id,
				type=EventType.NOTIFICATION_CUSTOM,
				data={"foo": "bar"},
				user_id=actor.id,
			),
			db_session,
			principal=principal,
		)

	err = excinfo.value
	assert getattr(err, "status_code", None) == 403


@pytest.mark.asyncio
async def test_persist_and_fanout_event_routes_user_scope_to_scope_id(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""For user-scoped events, scope_id is the recipient and user_id may be actor."""
	actor = User(
		email="route_actor@example.com",
		username="route_actor_test",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	target = User(
		email="route_target@example.com",
		username="route_target_test",
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

	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.USER,
			scope_id=target.id,
			type=EventType.FRIEND_REQUEST_SENT,
			data={"friendship_id": "f1"},
			user_id=actor.id,
		),
	)

	assert captured == [(None, target.id, False)]


@pytest.mark.asyncio
async def test_publish_task_event_routes_by_user_scope(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Task events use user scope before task access caches exist."""
	user = User(
		email="task_event_route@example.com",
		username="task_event_route",
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

	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.USER,
			scope_id=user.id,
			type=EventType.TASK_UPDATED,
			data={"task_id": new_typeid("task")},
			user_id=user.id,
		),
	)

	assert captured == [(None, user.id, False)]


@pytest.mark.parametrize(
	"event_type",
	[
		EventType.TOOL_PROGRESS,
		EventType.RUN_ACTIVITY_PROGRESS,
	],
)
@pytest.mark.asyncio
async def test_thread_progress_events_route_to_thread_readers(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
	event_type: EventType,
) -> None:
	"""Thread progress events use thread ACL fan-out, including readers."""
	owner = User(
		email="tool_owner@example.com",
		username="tool_owner",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	reader = User(
		email="tool_reader@example.com",
		username="tool_reader",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	outsider = User(
		email="tool_outsider@example.com",
		username="tool_outsider",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add_all([owner, reader, outsider])
	await db_session.flush()

	thread = Thread(owner_id=owner.id, title="shared tool thread")
	db_session.add(thread)
	await db_session.flush()
	db_session.add(
		AccessRule(
			thread_id=thread.id,
			subject_user_id=reader.id,
			level=AccessLevel.READER,
		)
	)
	await db_session.commit()

	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type=event_type,
			data={"thread_id": str(thread.id), "tool_call_id": "call_1"},
			user_id=owner.id,
			thread_id=thread.id,
		),
	)

	assert len(captured) == 1
	recipient_ids = captured[0][0]
	assert isinstance(recipient_ids, list)
	recipient_id_values = {str(value) for value in recipient_ids}
	assert str(owner.id) in recipient_id_values
	assert str(reader.id) in recipient_id_values
	assert str(outsider.id) not in recipient_id_values
	assert captured[0][1:] == (None, False)


@pytest.mark.asyncio
async def test_persist_and_fanout_event_broadcasts_system_scope(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""System scope is the explicit live broadcast target."""
	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.SYSTEM,
			type=EventType.SETTINGS_UPDATED,
			data={"updated_sections": ["general"]},
		),
	)

	assert captured == [(None, None, True)]


@pytest.mark.asyncio
async def test_persist_and_fanout_event_skips_unroutable_non_system_scope(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Unroutable non-system events are persisted without live delivery."""
	actor = User(
		email="unrouted_actor@example.com",
		username="unrouted_actor_test",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(actor)
	await db_session.commit()
	await db_session.refresh(actor)

	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.THREAD,
			type="custom.unrouted",
			data={},
			user_id=actor.id,
		),
	)

	assert captured == []


@pytest.mark.asyncio
async def test_persist_and_fanout_event_includes_owner_for_new_resource(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""Recipients must include the owner even when the resource row is still
	uncommitted in the caller's session.

	Regression: when ``persist_and_fanout_event`` resolved recipients before
	committing, a fresh read-only session could not see the pending INSERT for
	newly-created resources, so the owner was excluded from the recipient list
	and from the cached ``accessible_users`` entry. This blocked all subsequent
	THREAD-scope events (run.started, thread.updated, ...) from reaching the owner.
	"""
	owner = User(
		email="new_thread_owner@example.com",
		username="new_thread_owner",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(owner)
	await db_session.flush()

	thread = Thread(owner_id=owner.id, title="brand new thread")
	db_session.add(thread)
	await db_session.flush()

	captured: list[tuple[object, object, bool]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: object,
		user_id: object,
		broadcast: bool,
	) -> None:
		_ = stream_payload
		captured.append((recipient_ids, user_id, broadcast))

	monkeypatch.setattr(
		event_service,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await event_service.persist_and_fanout_event(
		db_session,
		Event(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type=EventType.THREAD_CREATED,
			data={"id": str(thread.id)},
			user_id=owner.id,
			thread_id=thread.id,
		),
	)

	assert len(captured) == 1
	recipient_ids = captured[0][0]
	assert isinstance(recipient_ids, list)
	recipient_id_values = {str(value) for value in recipient_ids}
	assert str(owner.id) in recipient_id_values


@pytest.mark.asyncio
async def test_resolve_event_recipients_includes_affected_project_viewers(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	resource_viewer = User(
		email="resource_viewer@example.com",
		username="resource_viewer",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	project_viewer = User(
		email="project_viewer@example.com",
		username="project_viewer",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add_all([resource_viewer, project_viewer])
	await db_session.flush()

	thread_id = new_typeid("thread")
	project_id = new_typeid("proj")
	calls: list[tuple[ResourceType, str]] = []

	async def fake_list_accessible_user_ids(
		resource_type: ResourceType,
		resource_id: TypeID,
		session: AsyncSession,
	) -> list[TypeID]:
		_ = session
		calls.append((resource_type, str(resource_id)))
		if resource_type == ResourceType.THREAD:
			return [resource_viewer.id]
		if resource_type == ResourceType.PROJECT:
			return [project_viewer.id, resource_viewer.id]
		return []

	monkeypatch.setattr(
		event_service,
		"list_accessible_user_ids",
		fake_list_accessible_user_ids,
	)

	recipients = await event_service._resolve_event_recipient_ids(
		Event(
			scope=EventScope.THREAD,
			scope_id=thread_id,
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"affected_project_ids": [str(project_id)],
			},
			thread_id=thread_id,
		)
	)

	assert {str(recipient_id) for recipient_id in recipients or []} == {
		str(resource_viewer.id),
		str(project_viewer.id),
	}
	assert calls == [
		(ResourceType.THREAD, str(thread_id)),
		(ResourceType.PROJECT, str(project_id)),
	]


@pytest.mark.asyncio
async def test_broadcast_run_event_uses_live_payload_fanout(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	owner = User(
		email="run_owner@example.com",
		username="run_owner",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(owner)
	await db_session.flush()

	thread = Thread(owner_id=owner.id, title="run thread")
	db_session.add(thread)
	await db_session.flush()
	owner_id = owner.id
	thread_id = thread.id
	await db_session.commit()

	stream_payloads: list[tuple[dict[str, object], list[object] | None]] = []

	async def fake_fanout_live_payload(
		stream_payload: dict[str, object],
		recipient_ids: list[object],
		user_id: object | None = None,
		broadcast: bool = False,
	) -> None:
		_ = user_id, broadcast
		stream_payloads.append((stream_payload, recipient_ids))

	monkeypatch.setattr(
		run_status,
		"fanout_live_payload",
		fake_fanout_live_payload,
	)

	await run_status.broadcast_run_event(
		thread_id=thread_id,
		agent_id=new_typeid("agent"),
		run_id=new_typeid("run"),
		started=True,
	)

	assert len(stream_payloads) == 1
	stream_payload, recipient_ids = stream_payloads[0]
	assert recipient_ids is not None
	assert str(owner_id) in {str(value) for value in recipient_ids}
	assert stream_payload["type"] == EventType.RUN_STARTED
	payload_data = stream_payload["data"]
	assert isinstance(payload_data, dict)
	assert any(
		key == "thread_id" and value == thread_id for key, value in payload_data.items()
	)


@pytest.mark.asyncio
async def test_list_events(db_session: AsyncSession) -> None:
	"""Test listing events."""
	principal = _admin_principal()
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
	event1 = await event_service.create_event_from_request(
		EventCreate(
			scope=EventScope.USER,
			scope_id=user.id,
			type="test.event.1",
			data={},
			user_id=user.id,
		),
		db_session,
		principal=principal,
	)
	event2 = await event_service.create_event_from_request(
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

	event3 = await event_service.create_event_from_request(
		EventCreate(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type="test.event.3",
			data={},
			thread_id=thread.id,
		),
		db_session,
		principal=principal,
	)

	# Emit event with task_id
	task = Task(user_id=user.id, task_type=TaskType.CUSTOM)
	db_session.add(task)
	await db_session.commit()
	await db_session.refresh(task)

	event4 = await event_service.create_event_from_request(
		EventCreate(
			scope=EventScope.TASK,
			scope_id=task.id,
			type="test.event.4",
			data={},
			task_id=task.id,
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
		principal=principal,
		filters=EventListFilters(user_id=user.id),
	)
	assert len(user_events) == 1
	assert user_events[0].id == event1.id

	# Filter by scope
	sys_events = await event_service.list_events(
		db_session,
		principal=principal,
		filters=EventListFilters(scope=EventScope.SYSTEM),
	)
	assert len(sys_events) >= 1
	assert event2.id in {e.id for e in sys_events}

	# Filter by since
	future_events = await event_service.list_events(
		db_session,
		principal=principal,
		filters=EventListFilters(since=datetime.now() + timedelta(hours=1)),
	)
	assert len(future_events) == 0

	# Filter by thread_id
	thread_events = await event_service.list_events(
		db_session,
		principal=principal,
		filters=EventListFilters(thread_id=thread.id),
	)
	assert len(thread_events) == 1
	assert thread_events[0].id == event3.id

	# Filter by task_id
	task_events = await event_service.list_events(
		db_session,
		principal=principal,
		filters=EventListFilters(task_id=task.id),
	)
	assert len(task_events) == 1
	assert task_events[0].id == event4.id


@pytest.mark.asyncio
async def test_events_router_endpoints(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Ensure the events router surfaces emitted events via HTTP."""
	headers_raw = admin_auth["headers"]
	assert isinstance(headers_raw, dict)
	headers = {str(key): str(value) for key, value in headers_raw.items()}
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
