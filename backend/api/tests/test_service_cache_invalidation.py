"""service-owned cache invalidation coverage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.event_types import EventType
from api.models.file import File, FileSource, FileStatus
from api.models.user import User
from api.permissions import (
	AccessLevel,
	DefaultPermissions,
	DefaultResourceAccess,
	ResourceType,
)
from api.schemas.agent import AgentConfig, AgentCreate, AgentUpdate
from api.schemas.calendar import (
	CalendarCreate,
	CalendarEventCreate,
	CalendarEventUpdate,
	CalendarUpdate,
)
from api.schemas.file import FileUpdate
from api.schemas.message import MessageCreate, MessageUpdate
from api.schemas.note import NoteCreate, NoteUpdate
from api.schemas.project import ProjectCreate, ProjectUpdate
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.schemas.reminder import (
	ReminderCreate,
	ReminderListCreate,
	ReminderListUpdate,
	ReminderUpdate,
)
from api.schemas.role import RoleCreate, RoleUpdate
from api.schemas.scheduled_item import (
	CalendarOccurrenceEdit,
	CalendarSeriesEdit,
	Recurrence,
	ReminderSeriesEdit,
)
from api.schemas.user import UserUpdate
from api.v1.service import agents as agent_service
from api.v1.service import files as file_service
from api.v1.service import notes as note_service
from api.v1.service import projects as project_service
from api.v1.service import prompts as prompt_service
from api.v1.service import roles as role_service
from api.v1.service import users as user_service
from api.v1.service.auth import Principal
from api.v1.service.calendar import calendars as calendar_service
from api.v1.service.calendar import events as calendar_event_service
from api.v1.service.reminders import core as reminder_service
from api.v1.service.reminders import lists as reminder_list_service
from api.v1.service.threads import core as thread_service
from api.v1.service.threads import messages as message_service
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _admin_principal(session: AsyncSession, label: str) -> Principal:
	user_id = new_typeid("user")
	user = User(
		email=f"{label}-{user_id}@example.com",
		username=f"{label}_{user_id.replace('_', '')[:16]}",
		hashed_password="x",
		is_superuser=True,
	)
	session.add(user)
	await session.flush()
	await session.refresh(user)
	return Principal(user=user, group_ids=(), permissions=frozenset())


async def _regular_user(session: AsyncSession, label: str) -> User:
	user_id = new_typeid("user")
	user = User(
		email=f"{label}-{user_id}@example.com",
		username=f"{label}_{user_id.replace('_', '')[:16]}",
		hashed_password="x",
		is_active=True,
		is_superuser=False,
	)
	session.add(user)
	await session.flush()
	await session.refresh(user)
	return user


def _utc(year: int, month: int, day: int, hour: int = 9) -> datetime:
	return datetime(year, month, day, hour, tzinfo=UTC)


@pytest.mark.asyncio
async def test_superuser_toggle_invalidates_all_accessible_user_caches(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "superuser-cache-admin")
	user = await _regular_user(db_session, "superuser-cache-user")
	calls: list[list[ResourceType]] = []

	async def record_resource_types(
		resource_types: list[ResourceType],
		session: AsyncSession,
	) -> None:
		_ = session
		calls.append(resource_types)

	monkeypatch.setattr(
		user_service,
		"invalidate_accessible_users_for_resource_types",
		record_resource_types,
	)

	await user_service.update_user(
		user.id,
		UserUpdate(is_superuser=True),
		db_session,
		principal=principal,
	)

	assert len(calls) == 1
	assert set(calls[0]) == set(ResourceType)


@pytest.mark.asyncio
async def test_thread_owner_transfer_invalidates_accessible_users_resource(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "owner-cache-admin")
	new_owner = await _regular_user(db_session, "owner-cache-user")
	calls: list[tuple[ResourceType, TypeID]] = []

	async def record_resource(
		resource_type: ResourceType,
		resource_id: TypeID,
	) -> None:
		calls.append((resource_type, resource_id))

	monkeypatch.setattr(
		thread_service,
		"invalidate_accessible_users_for_resource",
		record_resource,
	)

	thread = await thread_service.create_thread(
		thread_service.ThreadCreate(owner_id=principal.user_id, title="owner cache"),
		db_session,
		principal=principal,
	)
	calls.clear()

	await thread_service.update_thread(
		thread.id,
		thread_service.ThreadUpdate(owner_id=new_owner.id),
		db_session,
		principal=principal,
	)

	assert calls == [(ResourceType.THREAD, thread.id)]


@pytest.mark.asyncio
async def test_role_default_update_notifies_members_and_invalidates_defaults(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "role-cache-admin")
	member = await _regular_user(db_session, "role-cache-member")
	role_id = new_typeid("role")
	role = await role_service.create_role(
		RoleCreate(name=f"role-cache-{role_id.replace('_', '')[:16]}"),
		db_session,
		principal=principal,
	)
	await role_service.set_role_members(
		role.id,
		[member.id],
		db_session,
		principal=principal,
	)
	subject_calls: list[tuple[str, TypeID]] = []
	type_calls: list[list[ResourceType]] = []
	sent: list[tuple[list[TypeID] | None, str]] = []

	async def record_subject(
		subject_kind: str,
		subject_id: TypeID,
		session: AsyncSession,
	) -> None:
		_ = session
		subject_calls.append((subject_kind, subject_id))

	async def record_resource_types(
		resource_types: list[ResourceType],
		session: AsyncSession,
	) -> None:
		_ = session
		type_calls.append(resource_types)

	async def record_persist_and_fanout_event(
		session: AsyncSession,
		event: Event,
		origin_session_id: str | None = None,
		recipient_ids: list[TypeID] | None = None,
	) -> Event:
		_ = session
		_ = origin_session_id
		sent.append((recipient_ids, event.type))
		return event

	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_subject",
		record_subject,
	)
	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_resource_types",
		record_resource_types,
	)
	monkeypatch.setattr(
		role_service.event_service,
		"persist_and_fanout_event",
		record_persist_and_fanout_event,
	)

	await role_service.update_role(
		role.id,
		RoleUpdate(
			default_permissions=DefaultPermissions(
				resource_access=DefaultResourceAccess(thread=AccessLevel.READER)
			)
		),
		db_session,
		principal=principal,
	)

	assert subject_calls == [("role", role.id)]
	assert type_calls == [[ResourceType.THREAD]]
	assert len(sent) == 1
	assert sent[0][0] == [member.id]
	assert sent[0][1] == EventType.ROLE_UPDATED


@pytest.mark.asyncio
async def test_role_member_update_invalidates_role_default_resource_types(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "role-member-cache-admin")
	member = await _regular_user(db_session, "role-member-member")
	role_id = new_typeid("role")
	role = await role_service.create_role(
		RoleCreate(
			name=f"role-member-cache-{role_id.replace('_', '')[:16]}",
			default_permissions=DefaultPermissions(
				resource_access=DefaultResourceAccess(
					thread=AccessLevel.READER,
					calendar=AccessLevel.EDITOR,
				)
			),
		),
		db_session,
		principal=principal,
	)
	subject_calls: list[tuple[str, TypeID]] = []
	type_calls: list[list[ResourceType]] = []
	sent: list[tuple[list[TypeID] | None, str]] = []

	async def record_subject(
		subject_kind: str,
		subject_id: TypeID,
		session: AsyncSession,
	) -> None:
		_ = session
		subject_calls.append((subject_kind, subject_id))

	async def record_resource_types(
		resource_types: list[ResourceType],
		session: AsyncSession,
	) -> None:
		_ = session
		type_calls.append(resource_types)

	async def record_persist_and_fanout_event(
		session: AsyncSession,
		event: Event,
		origin_session_id: str | None = None,
		recipient_ids: list[TypeID] | None = None,
	) -> Event:
		_ = session
		_ = origin_session_id
		sent.append((recipient_ids, event.type))
		return event

	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_subject",
		record_subject,
	)
	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_resource_types",
		record_resource_types,
	)
	monkeypatch.setattr(
		role_service.event_service,
		"persist_and_fanout_event",
		record_persist_and_fanout_event,
	)

	await role_service.set_role_members(
		role.id,
		[member.id],
		db_session,
		principal=principal,
	)

	assert subject_calls == [("role", role.id)]
	assert len(type_calls) == 1
	assert set(type_calls[0]) == {ResourceType.THREAD, ResourceType.CALENDAR}
	assert sent == [([member.id], EventType.ROLE_UPDATED)]


@pytest.mark.asyncio
async def test_role_priority_update_does_not_invalidate_default_access(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "role-priority-admin")
	member = await _regular_user(db_session, "role-priority-member")
	role_id = new_typeid("role")
	role = await role_service.create_role(
		RoleCreate(
			name=f"role-priority-{role_id.replace('_', '')[:16]}",
			default_permissions=DefaultPermissions(
				resource_access=DefaultResourceAccess(thread=AccessLevel.READER)
			),
			priority=1,
		),
		db_session,
		principal=principal,
	)
	await role_service.set_role_members(
		role.id,
		[member.id],
		db_session,
		principal=principal,
	)
	subject_calls: list[tuple[str, TypeID]] = []
	type_calls: list[list[ResourceType]] = []
	sent: list[tuple[list[TypeID] | None, str]] = []

	async def record_subject(
		subject_kind: str,
		subject_id: TypeID,
		session: AsyncSession,
	) -> None:
		_ = session
		subject_calls.append((subject_kind, subject_id))

	async def record_resource_types(
		resource_types: list[ResourceType],
		session: AsyncSession,
	) -> None:
		_ = session
		type_calls.append(resource_types)

	async def record_persist_and_fanout_event(
		session: AsyncSession,
		event: Event,
		origin_session_id: str | None = None,
		recipient_ids: list[TypeID] | None = None,
	) -> Event:
		_ = session
		_ = origin_session_id
		sent.append((recipient_ids, event.type))
		return event

	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_subject",
		record_subject,
	)
	monkeypatch.setattr(
		role_service,
		"invalidate_accessible_users_for_resource_types",
		record_resource_types,
	)
	monkeypatch.setattr(
		role_service.event_service,
		"persist_and_fanout_event",
		record_persist_and_fanout_event,
	)

	await role_service.update_role(
		role.id,
		RoleUpdate(priority=99),
		db_session,
		principal=principal,
	)

	assert subject_calls == []
	assert type_calls == []
	assert sent == []


@pytest.mark.asyncio
async def test_cached_resource_write_paths_invalidate_payloads(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "resource-cache")
	calls: list[tuple[ResourceType, TypeID]] = []

	async def record_resource(
		resource_type: ResourceType,
		resource_id: TypeID,
	) -> None:
		calls.append((resource_type, resource_id))

	monkeypatch.setattr(
		agent_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)
	monkeypatch.setattr(
		file_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)
	monkeypatch.setattr(
		note_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)
	monkeypatch.setattr(
		project_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)
	monkeypatch.setattr(
		prompt_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)
	monkeypatch.setattr(
		thread_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)

	agent = await agent_service.create_agent(
		AgentCreate(name="cache-agent", plugin_ids=[], config=AgentConfig()),
		db_session,
		principal=principal,
	)
	await agent_service.update_agent(
		agent.id,
		AgentUpdate(description="updated"),
		db_session,
		principal=principal,
	)
	await agent_service.delete_agent(agent.id, db_session, principal=principal)

	file = File(
		owner_id=principal.user_id,
		source=FileSource.UPLOAD,
		storage_backend="local",
		storage_key="cache-invalidation-file",
		filename="before.txt",
		mime_type="text/plain",
		size_bytes=1,
		checksum_sha256=None,
		status=FileStatus.AVAILABLE,
	)
	db_session.add(file)
	await db_session.flush()
	await db_session.refresh(file)
	await file_service.update_file(
		file.id,
		FileUpdate(filename="after.txt"),
		db_session,
		principal=principal,
	)
	await file_service.delete_file(file.id, db_session, principal=principal)

	note = await note_service.create_note(
		NoteCreate(title="cache note", content="before", labels=[]),
		db_session,
		principal=principal,
	)
	await note_service.update_note(
		note.id,
		NoteUpdate(content="after"),
		db_session,
		principal=principal,
	)
	await note_service.delete_note(note.id, db_session, principal=principal)

	project = await project_service.create_project(
		ProjectCreate(name="cache project"),
		db_session,
		principal=principal,
	)
	await project_service.update_project(
		project.id,
		ProjectUpdate(description="after"),
		db_session,
		principal=principal,
	)
	await project_service.delete_project(project.id, db_session, principal=principal)

	thread = await thread_service.create_thread(
		thread_service.ThreadCreate(owner_id=principal.user_id, title="cache thread"),
		db_session,
		principal=principal,
	)
	await thread_service.update_thread(
		thread.id,
		thread_service.ThreadUpdate(title="after"),
		db_session,
		principal=principal,
	)
	await thread_service.delete_thread(thread.id, db_session, principal=principal)

	prompt = await prompt_service.create_prompt(
		PromptCreate(command="/cache-invalidation", content="before"),
		db_session,
		principal=principal,
	)
	await prompt_service.update_prompt(
		prompt.id,
		PromptUpdate(content="after"),
		db_session,
		principal=principal,
	)
	await prompt_service.delete_prompt(prompt.id, db_session, principal=principal)

	assert calls == [
		(ResourceType.AGENT, agent.id),
		(ResourceType.AGENT, agent.id),
		(ResourceType.FILE, file.id),
		(ResourceType.FILE, file.id),
		(ResourceType.NOTE, note.id),
		(ResourceType.NOTE, note.id),
		(ResourceType.PROJECT, project.id),
		(ResourceType.PROJECT, project.id),
		(ResourceType.THREAD, thread.id),
		(ResourceType.THREAD, thread.id),
		(ResourceType.PROMPT, prompt.id),
		(ResourceType.PROMPT, prompt.id),
	]


@pytest.mark.asyncio
async def test_thread_message_write_paths_invalidate_thread_payload(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "thread-cache")
	thread = await thread_service.create_thread(
		thread_service.ThreadCreate(owner_id=principal.user_id, title="messages"),
		db_session,
		principal=principal,
	)
	calls: list[tuple[ResourceType, TypeID]] = []

	async def record_resource(
		resource_type: ResourceType,
		resource_id: TypeID,
	) -> None:
		calls.append((resource_type, resource_id))

	monkeypatch.setattr(
		message_service,
		"invalidate_resource_payload_cache",
		record_resource,
	)

	first = await message_service.create_message(
		thread.id,
		MessageCreate(content="first"),
		db_session,
		principal=principal,
	)
	second = await message_service.create_message(
		thread.id,
		MessageCreate(content="second", parent_id=None),
		db_session,
		principal=principal,
	)
	await message_service.switch_branch(
		thread.id,
		first.id,
		db_session,
		principal=principal,
	)
	await message_service.update_user_message(
		thread.id,
		second.id,
		MessageUpdate(content="updated second"),
		db_session,
		principal=principal,
	)
	await message_service.delete_user_message_turn(
		thread.id,
		second.id,
		db_session,
		principal=principal,
	)

	assert calls == [(ResourceType.THREAD, thread.id)] * 5


@pytest.mark.asyncio
async def test_calendar_write_paths_invalidate_scheduled_item_cache(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "calendar-cache")
	calendar_calls: list[TypeID] = []
	event_calls: list[TypeID] = []

	async def record_calendar(calendar_id: TypeID) -> None:
		calendar_calls.append(calendar_id)

	async def record_calendar_event(event_id: TypeID) -> None:
		event_calls.append(event_id)

	monkeypatch.setattr(
		calendar_service,
		"invalidate_calendar_scheduled_items",
		record_calendar,
	)
	monkeypatch.setattr(
		calendar_event_service,
		"invalidate_calendar_event_scheduled_items",
		record_calendar_event,
	)

	start = _utc(2026, 5, 1)
	calendar = await calendar_service.create_calendar(
		CalendarCreate(name="cache calendar"),
		db_session,
		principal=principal,
	)
	event = await calendar_event_service.create_calendar_event(
		CalendarEventCreate(
			title="recurring event",
			start_at=start,
			end_at=start + timedelta(hours=1),
			recurrence=Recurrence(rrule=["FREQ=DAILY;COUNT=4"], timezone="UTC"),
		),
		db_session,
		principal=principal,
		calendar_id=calendar.id,
	)

	await calendar_event_service.update_calendar_event(
		event.id,
		CalendarEventUpdate(title="updated event"),
		db_session,
		principal=principal,
	)
	await calendar_event_service.edit_calendar_event_occurrence(
		event.id,
		CalendarOccurrenceEdit(
			original_occurrence_at=start + timedelta(days=1),
			title="edited occurrence",
		),
		db_session,
		principal=principal,
	)
	await calendar_event_service.cancel_calendar_event_occurrence(
		event.id,
		start + timedelta(days=2),
		db_session,
		principal=principal,
	)
	new_event = await calendar_event_service.edit_calendar_event_series(
		event.id,
		CalendarSeriesEdit(
			original_occurrence_at=start + timedelta(days=1),
			title="split event",
		),
		db_session,
		principal=principal,
	)
	await calendar_event_service.delete_calendar_event(
		new_event.id,
		db_session,
		principal=principal,
	)
	await calendar_service.update_calendar(
		calendar.id,
		CalendarUpdate(name="updated calendar"),
		db_session,
		principal=principal,
	)
	await calendar_service.delete_calendar(calendar.id, db_session, principal=principal)

	assert event_calls == [event.id, event.id, event.id, event.id, new_event.id]
	assert calendar_calls == [calendar.id, calendar.id]


@pytest.mark.asyncio
async def test_reminder_write_paths_invalidate_scheduled_item_cache(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	principal = await _admin_principal(db_session, "reminder-cache")
	list_calls: list[TypeID] = []
	reminder_calls: list[TypeID] = []

	async def record_list(list_id: TypeID) -> None:
		list_calls.append(list_id)

	async def record_reminder(reminder_id: TypeID) -> None:
		reminder_calls.append(reminder_id)

	monkeypatch.setattr(
		reminder_list_service,
		"invalidate_reminder_list_scheduled_items",
		record_list,
	)
	monkeypatch.setattr(
		reminder_service,
		"invalidate_reminder_scheduled_items",
		record_reminder,
	)

	start = _utc(2026, 6, 1)
	reminder_list = await reminder_list_service.create_reminder_list(
		ReminderListCreate(name="cache reminders"),
		db_session,
		principal=principal,
	)
	target_list = await reminder_list_service.create_reminder_list(
		ReminderListCreate(name="target reminders"),
		db_session,
		principal=principal,
	)
	recurring = await reminder_service.create_reminder(
		ReminderCreate(
			title="recurring reminder",
			list_id=reminder_list.id,
			due_at=start,
			recurrence=Recurrence(rrule=["FREQ=DAILY;COUNT=4"], timezone="UTC"),
		),
		db_session,
		principal=principal,
	)
	plain = await reminder_service.create_reminder(
		ReminderCreate(
			title="plain reminder",
			list_id=reminder_list.id,
			due_at=start,
		),
		db_session,
		principal=principal,
	)

	await reminder_service.update_reminder(
		recurring.id,
		ReminderUpdate(title="updated recurring"),
		db_session,
		principal=principal,
	)
	await reminder_service.complete_reminder_occurrence(
		recurring.id,
		start + timedelta(days=1),
		db_session,
		principal=principal,
	)
	new_reminder = await reminder_service.edit_reminder_series(
		recurring.id,
		ReminderSeriesEdit(
			original_occurrence_at=start + timedelta(days=2),
			title="split reminder",
		),
		db_session,
		principal=principal,
	)
	await reminder_service.move_reminder(
		new_reminder.id,
		target_list.id,
		db_session,
		principal=principal,
	)
	await reminder_service.delete_reminder(
		new_reminder.id,
		db_session,
		principal=principal,
	)
	await reminder_service.complete_reminder(
		plain.id,
		db_session,
		principal=principal,
	)
	await reminder_list_service.update_reminder_list(
		reminder_list.id,
		ReminderListUpdate(name="updated reminders"),
		db_session,
		principal=principal,
	)
	await reminder_list_service.delete_reminder_list(
		target_list.id,
		db_session,
		principal=principal,
	)
	await reminder_list_service.delete_reminder_list(
		reminder_list.id,
		db_session,
		principal=principal,
	)

	assert reminder_calls == [
		recurring.id,
		recurring.id,
		recurring.id,
		new_reminder.id,
		new_reminder.id,
		plain.id,
	]
	assert list_calls == [reminder_list.id, target_list.id, reminder_list.id]
