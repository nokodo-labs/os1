"""Additional service branch coverage."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.agent import Agent
from api.models.event import Event, EventScope
from api.models.memory import Memory
from api.models.message import MessageType
from api.models.notification import Notification
from api.models.task import Task, TaskStatus, TaskType
from api.models.thread import Thread
from api.models.user import User
from api.schemas.agent import AgentConfig, AgentCreate
from api.schemas.memory import MemoryListFilters
from api.schemas.message import MessageCreate
from api.schemas.task import TaskListFilters, TaskUpdate
from api.schemas.user import UserCreate
from api.v1.service import (
	agents,
	authorization,
	memories,
	notifications,
	tasks,
	threads,
	users,
)
from api.v1.service.auth import Principal, authenticate_user, get_current_active_user
from nokodo_ai.utils.security import hash_password
from nokodo_ai.utils.typeid import TypeID, new_typeid


def _user(is_admin: bool = False, active: bool = True) -> User:
	uid = new_typeid("user")
	return User(
		email=f"u-{uid}@example.com",
		username=f"u{uid[-12:]}",
		hashed_password=hash_password("password"),
		is_active=active,
		is_superuser=is_admin,
	)


async def _principal(
	user: User,
	session: AsyncSession | None = None,
) -> Principal:
	if session is not None and user.id is None:
		session.add(user)
		await session.flush()
	return Principal(user=user, group_ids=(), permissions=frozenset())


@pytest.mark.asyncio
async def test_authenticate_user_paths(db_session: AsyncSession) -> None:
	user = _user()
	db_session.add(user)
	await db_session.commit()
	assert await authenticate_user(db_session, user.email, "password") is not None
	assert await authenticate_user(db_session, user.email, "wrong") is None
	assert (
		await authenticate_user(db_session, "missing@example.com", "password") is None
	)


@pytest.mark.asyncio
async def test_principal_permission_checks() -> None:
	user = _user()
	principal = Principal(
		user=user, group_ids=(), permissions=frozenset({"foo:read", "bar:*"})
	)
	assert principal.has_permission("foo:read")
	assert principal.has_permission("bar:write")
	assert not principal.has_permission("baz:read")
	admin = Principal(user=_user(is_admin=True), group_ids=(), permissions=frozenset())
	assert admin.has_permission("anything")


@pytest.mark.asyncio
async def test_get_current_active_user_guard() -> None:
	inactive = _user(active=False)
	with pytest.raises(HTTPException):
		await get_current_active_user(inactive)


@pytest.mark.asyncio
async def test_authorization_require_access(db_session: AsyncSession) -> None:
	user = _user()
	db_session.add(user)
	await db_session.commit()
	principal = await _principal(user, session=db_session)
	with pytest.raises(HTTPException):
		await authorization.require_thread_access(
			new_typeid("thread"), db_session, principal=principal
		)
	with pytest.raises(HTTPException):
		await authorization.require_project_access(
			new_typeid("proj"), db_session, principal=principal
		)


@pytest.mark.asyncio
async def test_agents_visibility_and_model_check(db_session: AsyncSession) -> None:
	admin = await _principal(_user(is_admin=True), session=db_session)
	with pytest.raises(HTTPException):
		await agents.create_agent(
			agent_in=AgentCreate(
				model_id=new_typeid("model"),
				name="bad",
				description=None,
				system_prompt=None,
				plugin_ids=[],
				config=AgentConfig(),
			),
			session=db_session,
			principal=admin,
		)

	# private agent hidden from non-admins
	owner = _user()
	private_agent = Agent(
		name="private",
		description=None,
		system_prompt=None,
		plugin_ids=[],
		config={},
		model_id=None,
	)
	db_session.add_all([owner, private_agent])
	await db_session.commit()
	non_admin = await _principal(owner, session=db_session)
	with pytest.raises(HTTPException):
		await agents.get_agent(private_agent.id, db_session, principal=non_admin)


@pytest.mark.asyncio
async def test_notifications_guards(db_session: AsyncSession) -> None:
	user_a = _user()
	user_b = _user()
	db_session.add_all([user_a, user_b])
	await db_session.commit()
	event = Event(
		scope=EventScope.USER, scope_id=user_a.id, type="t", data={}, user_id=user_a.id
	)
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
	principal_b = await _principal(user_b, session=db_session)
	with pytest.raises(HTTPException):
		await notifications.mark_notification_read(
			note.id, db_session, principal=principal_b
		)
	principal_a = await _principal(user_a, session=db_session)
	marked = await notifications.mark_notification_read(
		note.id, db_session, principal=principal_a
	)
	assert marked.read_at is not None
	dismissed = await notifications.dismiss_notification(
		note.id, db_session, principal=principal_a
	)
	assert dismissed.dismissed is True


@pytest.mark.asyncio
async def test_tasks_update_no_changes(db_session: AsyncSession) -> None:
	user = _user()
	db_session.add(user)
	await db_session.commit()
	principal = await _principal(user, session=db_session)
	task = Task(
		id=TypeID(new_typeid("task")),
		user_id=user.id,
		status=TaskStatus.PENDING,
		task_type=TaskType.CUSTOM,
	)
	db_session.add(task)
	await db_session.commit()
	unchanged = await tasks.update_task(
		task.id, TaskUpdate(), db_session, principal=principal
	)
	assert unchanged.last_event_at is None
	filtered = await tasks.list_tasks(
		db_session,
		principal=principal,
		filters=TaskListFilters(status_filter=TaskStatus.PENDING),
	)
	assert filtered


@pytest.mark.asyncio
async def test_memories_admin_user_filter(db_session: AsyncSession) -> None:
	admin_user = _user(is_admin=True)
	other_user = _user()
	db_session.add_all([admin_user, other_user])
	await db_session.commit()
	principal = await _principal(admin_user, session=db_session)
	memory = Memory(
		id=TypeID(new_typeid("mem")),
		user_id=other_user.id,
		content="c",
	)
	db_session.add(memory)
	await db_session.commit()
	listed = await memories.list_memories(
		db_session,
		principal=principal,
		filters=MemoryListFilters(owner_id=other_user.id),
	)
	assert listed and listed[0].user_id == other_user.id


@pytest.mark.asyncio
async def test_users_guards(db_session: AsyncSession) -> None:
	user = _user()
	db_session.add(user)
	await db_session.commit()
	principal = await _principal(user, session=db_session)
	with pytest.raises(HTTPException):
		await users.list_users(db_session, principal=principal)

	with pytest.raises(HTTPException):
		await users.get_user(new_typeid("user"), db_session, principal=principal)

	created = await users.create_user(
		user_in=UserCreate(
			email="x@example.com",
			username="x_test_sb",
			password="pw",
			is_superuser=True,
		),
		session=db_session,
		principal=None,
	)
	assert created.is_active is True
	assert created.is_superuser is False

	with pytest.raises(HTTPException):
		await users.create_user(
			user_in=UserCreate(
				email="y@example.com", username="y_test_sb", password="pw"
			),
			session=db_session,
			principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		)

	user.is_active = False
	with pytest.raises(HTTPException):
		await users.create_user(
			user_in=UserCreate(
				email="z@example.com",
				username="z_test_sb",
				password="pw",
				is_active=True,
			),
			session=db_session,
			principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		)


@pytest.mark.asyncio
async def test_thread_update_owner_and_create_message(db_session: AsyncSession) -> None:
	owner = _user()
	new_owner = _user()
	db_session.add_all([owner, new_owner])
	await db_session.commit()
	thread = Thread(
		id=TypeID(new_typeid("thread")),
		owner_id=owner.id,
		title="t",
	)
	db_session.add(thread)
	await db_session.commit()
	admin = await _principal(_user(is_admin=True), session=db_session)
	updated = await threads.update_thread(
		thread.id,
		threads.ThreadUpdate(owner_id=new_owner.id),
		db_session,
		principal=admin,
	)
	assert updated.owner_id == new_owner.id

	msg = await threads.create_message(
		thread.id,
		MessageCreate(content="c", type=MessageType.USER),
		db_session,
		principal=admin,
	)
	assert msg.thread_id == thread.id
