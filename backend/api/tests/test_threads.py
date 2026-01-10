"""Thread-specific tests."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.acl import AccessControlEntry, AccessRole
from api.models.message import MessageType
from api.models.project import Project
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.mark.asyncio
async def test_thread_project_association(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Threads can belong to multiple projects and be reassigned."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	project_a = Project(name="Project A", description="A", owner_id=user["id"])
	project_b = Project(name="Project B", description="B", owner_id=user["id"])
	db_session.add_all([project_a, project_b])
	await db_session.commit()
	await db_session.refresh(project_a)
	await db_session.refresh(project_b)

	thread_payload = {
		"owner_id": user["id"],
		"title": "Multi-project thread",
		"project_ids": [project_a.id, project_b.id],
	}
	thread_resp = await client.post("/v1/threads", json=thread_payload, headers=headers)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()
	assert set(thread["project_ids"]) == {project_a.id, project_b.id}
	assert len(thread["projects"]) == 2

	update_resp = await client.patch(
		f"/v1/threads/{thread['id']}",
		json={"project_ids": [project_b.id]},
		headers=headers,
	)
	assert update_resp.status_code == 200
	updated_thread = update_resp.json()
	assert set(updated_thread["project_ids"]) == {project_b.id}


@pytest.mark.asyncio
async def test_create_thread_basic(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test creating a thread without projects."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_payload = {
		"owner_id": user["id"],
		"title": "Basic Thread",
	}
	thread_resp = await client.post("/v1/threads", json=thread_payload, headers=headers)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()
	assert thread["title"] == "Basic Thread"
	assert thread["owner_id"] == user["id"]
	assert thread["project_ids"] == []


@pytest.mark.asyncio
async def test_list_threads(client: AsyncClient, user_auth: dict[str, object]) -> None:
	"""Test listing threads."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	# Create 2 threads
	await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "T1"},
		headers=headers,
	)
	await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "T2"},
		headers=headers,
	)

	resp = await client.get(f"/v1/threads?owner_id={user['id']}", headers=headers)
	assert resp.status_code == 200
	threads = resp.json()
	assert len(threads) == 2
	titles = {t["title"] for t in threads}
	assert titles == {"T1", "T2"}


@pytest.mark.asyncio
async def test_list_threads_sorting(
	client: AsyncClient, user_auth: dict[str, object]
) -> None:
	"""List threads supports server-side sort_by + sort_dir."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "b"},
		headers=headers,
	)
	await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "a"},
		headers=headers,
	)

	resp = await client.get(
		"/v1/threads",
		headers=headers,
		params={
			"owner_id": user["id"],
			"sort_by": "title",
			"sort_dir": "asc",
		},
	)
	assert resp.status_code == 200
	threads = resp.json()
	assert [t["title"] for t in threads] == ["a", "b"]


@pytest.mark.asyncio
async def test_temporary_threads_hidden_by_default(
	client: AsyncClient,
	user_auth: dict[str, object],
	admin_auth: dict[str, object],
) -> None:
	"""Temporary threads are persisted but hidden unless admin opts in."""
	user_headers = user_auth["headers"]
	assert isinstance(user_headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	create_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "Temp", "is_temporary": True},
		headers=user_headers,
	)
	assert create_resp.status_code == 201
	temp_thread_id = create_resp.json()["id"]

	user_list = await client.get(
		f"/v1/threads?owner_id={user['id']}",
		headers=user_headers,
	)
	assert user_list.status_code == 200
	assert temp_thread_id not in {t["id"] for t in user_list.json()}

	user_get = await client.get(f"/v1/threads/{temp_thread_id}", headers=user_headers)
	assert user_get.status_code == 404

	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)

	admin_default_list = await client.get("/v1/threads", headers=admin_headers)
	assert admin_default_list.status_code == 200
	assert temp_thread_id not in {t["id"] for t in admin_default_list.json()}

	admin_hidden_list = await client.get(
		"/v1/threads",
		headers=admin_headers,
		params={"include_hidden": True},
	)
	assert admin_hidden_list.status_code == 200
	assert temp_thread_id in {t["id"] for t in admin_hidden_list.json()}

	admin_get_hidden = await client.get(
		f"/v1/threads/{temp_thread_id}",
		headers=admin_headers,
		params={"include_hidden": True},
	)
	assert admin_get_hidden.status_code == 200
	assert admin_get_hidden.json()["is_temporary"] is True


@pytest.mark.asyncio
async def test_soft_deleted_threads_hidden(
	client: AsyncClient,
	user_auth: dict[str, object],
	admin_auth: dict[str, object],
	db_session: AsyncSession,
) -> None:
	"""Soft-deleted threads stay hidden except for explicit admin queries."""
	user_headers = user_auth["headers"]
	assert isinstance(user_headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	create_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "Soft Delete"},
		headers=user_headers,
	)
	assert create_resp.status_code == 201
	thread_id = create_resp.json()["id"]

	thread_orm = await db_session.get(Thread, thread_id)
	assert thread_orm is not None
	pre_delete_threads = list((await db_session.scalars(select(Thread))).all())
	assert len(pre_delete_threads) == 1
	thread_orm.soft_delete()
	await db_session.commit()
	raw_threads = list(
		(await db_session.execute(text("SELECT id, deleted_at FROM threads"))).all()
	)
	assert raw_threads, "raw query found no threads"

	user_list = await client.get(
		f"/v1/threads?owner_id={user['id']}",
		headers=user_headers,
	)
	assert user_list.status_code == 200
	assert thread_id not in {t["id"] for t in user_list.json()}

	user_get = await client.get(f"/v1/threads/{thread_id}", headers=user_headers)
	assert user_get.status_code == 404

	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)

	admin_default_list = await client.get("/v1/threads", headers=admin_headers)
	assert admin_default_list.status_code == 200
	assert thread_id not in {t["id"] for t in admin_default_list.json()}

	admin_hidden_list = await client.get(
		"/v1/threads",
		headers=admin_headers,
		params={"include_hidden": True},
	)
	assert admin_hidden_list.status_code == 200
	admin_user = await db_session.get(User, admin_auth["user"]["id"])
	assert admin_user is not None
	admin_principal = Principal(user=admin_user, group_ids=(), permissions=frozenset())
	all_threads = list(
		(
			await db_session.scalars(
				select(Thread).execution_options(include_deleted=True)
			)
		).all()
	)
	assert all_threads, "no threads persisted"
	service_threads = await thread_service.list_threads(
		db_session,
		principal=admin_principal,
		include_hidden=True,
	)
	service_ids = {str(t.id) for t in service_threads}
	assert thread_id in service_ids

	admin_hidden_body = admin_hidden_list.json()
	assert thread_id in {t["id"] for t in admin_hidden_body}, {
		"api_body": admin_hidden_body,
		"service_ids": list(service_ids),
	}

	admin_get_hidden = await client.get(
		f"/v1/threads/{thread_id}",
		headers=admin_headers,
		params={"include_hidden": True},
	)
	assert admin_get_hidden.status_code == 200
	assert admin_get_hidden.json()["id"] == thread_id


@pytest.mark.asyncio
async def test_thread_messages(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test creating and listing messages in a thread."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "Msg Thread"},
		headers=headers,
	)
	thread_id = thread_resp.json()["id"]

	# Create user message
	msg_payload = {
		"content": "Hello AI",
		"type": "user",
		"sender_user_id": user["id"],
	}
	msg_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=msg_payload,
		headers=headers,
	)
	assert msg_resp.status_code == 201
	msg = msg_resp.json()
	# Content is now a list of content parts
	assert msg["content"] == [{"type": "text", "text": "Hello AI", "metadata": None}]
	assert msg["type"] == "user"

	# List messages
	list_resp = await client.get(f"/v1/threads/{thread_id}/messages", headers=headers)
	assert list_resp.status_code == 200
	messages = list_resp.json()
	assert len(messages) == 1
	assert messages[0]["id"] == msg["id"]


@pytest.mark.asyncio
async def test_thread_messages_group_task_runs(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "group runs"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	run_id = "run-test-1"
	tool_call_id_1 = "tool_call_test_1"
	tool_call_id_2 = "tool_call_test_2"

	assistant_payload = {
		"content": "calling tools",
		"type": "assistant",
		"metadata_": {"run_id": run_id},
		"tool_calls": [
			{"id": tool_call_id_1, "name": "t1", "arguments": {}},
			{"id": tool_call_id_2, "name": "t2", "arguments": {}},
		],
	}
	assistant_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=assistant_payload,
		headers=headers,
	)
	assert assistant_resp.status_code == 201
	assistant_msg = assistant_resp.json()

	tool_payload_1 = {
		"content": "tool out 1",
		"type": "tool",
		"tool_call_id": tool_call_id_1,
		"is_error": False,
		"metadata_": {"run_id": run_id},
	}
	tool_payload_2 = {
		"content": "tool out 2",
		"type": "tool",
		"tool_call_id": tool_call_id_2,
		"is_error": False,
		"metadata_": {"run_id": run_id},
	}
	tool_resp_1 = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=tool_payload_1,
		headers=headers,
	)
	assert tool_resp_1.status_code == 201
	tool_msg_1 = tool_resp_1.json()

	tool_resp_2 = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=tool_payload_2,
		headers=headers,
	)
	assert tool_resp_2.status_code == 201
	tool_msg_2 = tool_resp_2.json()

	# With grouping enabled, requesting a small page that lands on tool messages
	# should stitch in the initiating assistant message (but not the entire run).
	list_resp = await client.get(
		f"/v1/threads/{thread_id}/messages",
		headers=headers,
		params={"limit": 1},
	)
	assert list_resp.status_code == 200
	items = list_resp.json()
	assert len(items) == 2
	assert items[0]["id"] in {tool_msg_1["id"], tool_msg_2["id"]}
	assert items[1]["id"] == assistant_msg["id"]
	assert items[1]["type"] == "assistant"

	list_resp_no_group = await client.get(
		f"/v1/threads/{thread_id}/messages",
		headers=headers,
		params={"limit": 1, "group_task_runs": False},
	)
	assert list_resp_no_group.status_code == 200
	items_no_group = list_resp_no_group.json()
	assert len(items_no_group) == 1
	assert items_no_group[0]["type"] == "tool"


@pytest.mark.asyncio
async def test_create_thread_invalid_user(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""Test creating a thread with non-existent user."""
	headers = admin_auth["headers"]
	assert isinstance(headers, dict)
	thread_payload = {
		"owner_id": new_typeid("user"),
		"title": "Invalid User Thread",
	}
	resp = await client.post("/v1/threads", json=thread_payload, headers=headers)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_create_thread_invalid_project(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test creating a thread with non-existent project."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_payload = {
		"owner_id": user["id"],
		"title": "Invalid Project Thread",
		"project_ids": [new_typeid("proj")],
	}
	resp = await client.post("/v1/threads", json=thread_payload, headers=headers)
	assert resp.status_code == 404
	assert "Projects not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_service_create_thread(db_session: AsyncSession) -> None:
	"""Test creating a thread directly via service."""
	# Create user
	from api.models.user import User

	user = User(
		email="service@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread_in = ThreadCreate(
		owner_id=user.id,
		title="Service Thread",
	)
	thread = await thread_service.create_thread(
		thread_in,
		db_session,
		principal=principal,
	)
	assert thread.title == "Service Thread"
	assert thread.owner_id == user.id


@pytest.mark.asyncio
async def test_get_thread_not_found(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test getting a non-existent thread."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	resp = await client.get(f"/v1/threads/{new_typeid('thread')}", headers=headers)
	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_thread_owner(
	client: AsyncClient,
	admin_auth: dict[str, object],
	user_auth: dict[str, object],
) -> None:
	"""Test updating thread owner."""
	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)
	user1 = user_auth["user"]
	assert isinstance(user1, dict)
	user1_headers = user_auth["headers"]
	assert isinstance(user1_headers, dict)

	user2_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": "u2@example.com",
			"password": "password",
		},
	)
	assert user2_resp.status_code == 201
	user2 = user2_resp.json()

	# Create thread with user1
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user1["id"], "title": "Owner Update"},
		headers=user1_headers,
	)
	thread_id = thread_resp.json()["id"]

	# Update owner to user2
	update_resp = await client.patch(
		f"/v1/threads/{thread_id}",
		json={"owner_id": user2["id"]},
		headers=user1_headers,
	)
	assert update_resp.status_code == 200
	updated = update_resp.json()
	assert updated["owner_id"] == user2["id"]


@pytest.mark.asyncio
async def test_create_message_types(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""Test creating different message types."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "Message Types"},
		headers=headers,
	)
	thread_id = thread_resp.json()["id"]

	# Assistant Message
	asst_msg = {
		"type": "assistant",
		"content": "Hello",
		"sender_agent_id": None,  # Optional
	}
	resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=asst_msg,
		headers=headers,
	)
	assert resp.status_code == 201
	assert resp.json()["type"] == "assistant"

	# System Message
	sys_msg = {
		"type": "system",
		"content": "System Prompt",
	}
	resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json=sys_msg,
		headers=headers,
	)
	assert resp.status_code == 201
	assert resp.json()["type"] == "system"


@pytest.mark.asyncio
async def test_service_create_thread_missing_owner(db_session: AsyncSession) -> None:
	admin = User(
		email="thread-admin@example.com",
		hashed_password="pw",
		is_active=True,
		is_superuser=True,
	)
	db_session.add(admin)
	await db_session.commit()
	principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	with pytest.raises(HTTPException):
		await thread_service.create_thread(
			ThreadCreate(owner_id=new_typeid("user"), title="missing"),
			db_session,
			principal=principal,
		)


@pytest.mark.asyncio
async def test_update_thread_owner_guard(db_session: AsyncSession) -> None:
	owner = User(email="owner@example.com", hashed_password="pw", is_active=True)
	editor = User(email="editor@example.com", hashed_password="pw", is_active=True)
	db_session.add_all([owner, editor])
	await db_session.commit()

	owner_principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=owner.id, title="guard"),
		db_session,
		principal=owner_principal,
	)
	ace = AccessControlEntry(
		id=TypeID(new_typeid("acl")),
		thread_id=thread.id,
		user_id=editor.id,
		role=AccessRole.EDITOR,
	)
	db_session.add(ace)
	await db_session.commit()

	editor_principal = Principal(user=editor, group_ids=(), permissions=frozenset())
	with pytest.raises(HTTPException):
		await thread_service.update_thread(
			thread.id,
			ThreadUpdate(owner_id=editor.id),
			db_session,
			principal=editor_principal,
		)


@pytest.mark.asyncio
async def test_update_thread_new_owner_missing(db_session: AsyncSession) -> None:
	admin = User(
		email="owner-missing@example.com",
		hashed_password="pw",
		is_active=True,
		is_superuser=True,
	)
	db_session.add(admin)
	await db_session.commit()
	principal = Principal(user=admin, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=admin.id, title="missing-owner"),
		db_session,
		principal=principal,
	)

	with pytest.raises(HTTPException):
		await thread_service.update_thread(
			thread.id,
			ThreadUpdate(owner_id=new_typeid("user")),
			db_session,
			principal=principal,
		)


@pytest.mark.asyncio
async def test_update_thread_owner_handoff_returns_unrestricted(
	db_session: AsyncSession,
) -> None:
	owner = User(
		email="handoff-owner@example.com", hashed_password="pw", is_active=True
	)
	new_owner = User(
		email="handoff-new@example.com", hashed_password="pw", is_active=True
	)
	db_session.add_all([owner, new_owner])
	await db_session.commit()

	principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=owner.id, title="handoff"),
		db_session,
		principal=principal,
	)

	orig = thread_service._load_thread
	called = False
	seen_principal: Principal | None = None

	async def _tracking(
		thread_id: TypeID,
		session: AsyncSession,
		principal: Principal | None = None,
		*,
		required_role: AccessRole = AccessRole.VIEWER,
		include_hidden: bool = False,
	) -> thread_service.Thread:
		nonlocal called
		nonlocal seen_principal
		called = True
		seen_principal = principal
		return await orig(
			thread_id,
			session,
			principal,
			required_role=required_role,
			include_hidden=include_hidden,
		)

	thread_service._load_thread = _tracking
	try:
		updated = await thread_service.update_thread(
			thread.id,
			ThreadUpdate(owner_id=new_owner.id),
			db_session,
			principal=principal,
		)
	finally:
		thread_service._load_thread = orig
	assert called
	assert seen_principal is None
	assert updated.owner_id == new_owner.id


@pytest.mark.asyncio
async def test_load_thread_unrestricted_missing(db_session: AsyncSession) -> None:
	with pytest.raises(HTTPException):
		await thread_service._load_thread(
			TypeID(new_typeid("thread")),
			db_session,
			None,
		)


@pytest.mark.asyncio
async def test_create_message_sender_guard(db_session: AsyncSession) -> None:
	owner = User(email="sender-owner@example.com", hashed_password="pw", is_active=True)
	other = User(email="sender-other@example.com", hashed_password="pw", is_active=True)
	db_session.add_all([owner, other])
	await db_session.commit()

	principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=owner.id, title="sender-guard"),
		db_session,
		principal=principal,
	)

	with pytest.raises(HTTPException):
		await thread_service.create_message(
			thread.id,
			MessageCreate(
				content="forbidden",
				type=MessageType.USER,
				sender_user_id=other.id,
			),
			db_session,
			principal=principal,
		)


@pytest.mark.asyncio
async def test_get_thread_not_found_service(db_session: AsyncSession) -> None:
	from api.models.user import User

	user = User(
		email="svc_not_found@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=True,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(user)
	await db_session.commit()
	await db_session.refresh(user)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	with pytest.raises(HTTPException) as exc:
		await thread_service.get_thread("nonexistent", db_session, principal=principal)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_invalid_user_service(db_session: AsyncSession) -> None:
	from api.models.user import User

	admin = User(
		email="svc_invalid_owner@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=True,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(admin)
	await db_session.commit()
	await db_session.refresh(admin)
	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())

	thread_in = ThreadCreate(owner_id=new_typeid("user"), title="Test")
	with pytest.raises(HTTPException) as exc:
		await thread_service.create_thread(
			thread_in,
			db_session,
			principal=admin_principal,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_invalid_project_service(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	user = User(
		email="svc_invalid_project@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread_in = ThreadCreate(
		owner_id=user.id,
		title="Test",
		project_ids=[new_typeid("proj")],
	)
	with pytest.raises(HTTPException) as exc:
		await thread_service.create_thread(thread_in, db_session, principal=principal)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_threads_filter_owner(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	user = User(
		email="svc_list_owner@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread_in = ThreadCreate(owner_id=user.id, title="Test")
	await thread_service.create_thread(thread_in, db_session, principal=principal)

	threads = await thread_service.list_threads(
		db_session,
		principal=principal,
		owner_id=user.id,
	)
	assert len(threads) == 1
	assert threads[0].owner_id == user.id

	threads_empty = await thread_service.list_threads(
		db_session,
		principal=principal,
		owner_id=new_typeid("user"),
	)
	assert len(threads_empty) == 0


@pytest.mark.asyncio
async def test_update_thread_owner_service(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	u1 = User(
		email="svc_u1@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	u2 = User(
		email="svc_u2@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add_all([u1, u2])
	await db_session.commit()
	await db_session.refresh(u1)
	await db_session.refresh(u2)
	principal = Principal(user=u1, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=u1.id, title="T"),
		db_session,
		principal=principal,
	)

	updated = await thread_service.update_thread(
		thread.id,
		ThreadUpdate(owner_id=u2.id),
		db_session,
		principal=principal,
	)
	assert updated.owner_id == u2.id


@pytest.mark.asyncio
async def test_update_thread_fields_service(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	owner = User(
		email="svc_update_fields@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add(owner)
	await db_session.commit()
	await db_session.refresh(owner)
	principal = Principal(user=owner, group_ids=(), permissions=frozenset())

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=owner.id, title="initial", tags=["t1"]),
		db_session,
		principal=principal,
	)

	updated = await thread_service.update_thread(
		thread.id,
		ThreadUpdate(title="updated", tags=["t2"], is_archived=True),
		db_session,
		principal=principal,
	)
	assert updated.title == "updated"
	assert updated.tags == ["t2"]
	assert updated.is_archived is True


@pytest.mark.asyncio
async def test_admin_update_owner_and_create_message(
	db_session: AsyncSession,
) -> None:
	"""Admin can reassign owner and post a message."""
	from api.models.user import User

	owner = User(
		email="admin-thread-owner@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	new_owner = User(
		email="admin-thread-new@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	admin = User(
		email="admin-thread-admin@example.com",
		hashed_password="password",
		is_active=True,
		is_superuser=True,
		preferences={},
		integration_tokens={},
		usage_quotas={},
	)
	db_session.add_all([owner, new_owner, admin])
	await db_session.commit()
	await db_session.refresh(owner)
	await db_session.refresh(new_owner)
	await db_session.refresh(admin)

	owner_principal = Principal(user=owner, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=owner.id, title="admin-transfer"),
		db_session,
		principal=owner_principal,
	)

	admin_principal = Principal(user=admin, group_ids=(), permissions=frozenset())
	updated = await thread_service.update_thread(
		thread.id,
		ThreadUpdate(owner_id=new_owner.id),
		db_session,
		principal=admin_principal,
	)
	assert updated.owner_id == new_owner.id

	msg = await thread_service.create_message(
		thread.id,
		MessageCreate(content="admin msg", type=MessageType.USER),
		db_session,
		principal=admin_principal,
	)
	assert msg.thread_id == thread.id


@pytest.mark.asyncio
async def test_create_message_types_service(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	user = User(
		email="svc_msgs@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="T"),
		db_session,
		principal=principal,
	)

	# Assistant
	msg_asst = await thread_service.create_message(
		thread.id,
		MessageCreate(content="A", type=MessageType.ASSISTANT, sender_user_id=user.id),
		db_session,
		principal=principal,
	)
	assert msg_asst.type == MessageType.ASSISTANT

	# Tool
	msg_tool = await thread_service.create_message(
		thread.id,
		MessageCreate(
			content="T",
			type=MessageType.TOOL,
			tool_call_id=TypeID(new_typeid("tool_call")),
			is_error=False,
			sender_user_id=user.id,
		),
		db_session,
		principal=principal,
	)
	assert msg_tool.type == MessageType.TOOL

	# System
	msg_sys = await thread_service.create_message(
		thread.id,
		MessageCreate(content="S", type=MessageType.SYSTEM, sender_user_id=user.id),
		db_session,
		principal=principal,
	)
	assert msg_sys.type == MessageType.SYSTEM


@pytest.mark.asyncio
async def test_create_message_unknown_type_service(
	db_session: AsyncSession,
) -> None:
	"""Ensure unexpected message types fall back to user messages."""
	from api.models.user import User

	user = User(
		email="svc_unknown_type@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="Unknown"),
		db_session,
		principal=principal,
	)
	message_in = MessageCreate.model_construct(
		content="Fallback",
		sender_user_id=user.id,
		type=cast(Any, "custom"),
	)
	message = await thread_service.create_message(
		thread.id,
		message_in,
		db_session,
		principal=principal,
	)
	assert message.type == MessageType.USER


@pytest.mark.asyncio
async def test_list_messages_service(
	db_session: AsyncSession,
) -> None:
	from api.models.user import User

	user = User(
		email="svc_list_msgs@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="T"),
		db_session,
		principal=principal,
	)

	await thread_service.create_message(
		thread.id,
		MessageCreate(content="1", sender_user_id=user.id),
		db_session,
		principal=principal,
	)
	await thread_service.create_message(
		thread.id,
		MessageCreate(content="2", sender_user_id=user.id),
		db_session,
		principal=principal,
	)

	msgs = await thread_service.list_messages(
		thread.id,
		db_session,
		principal=principal,
	)
	assert len(msgs) == 2


@pytest.mark.asyncio
async def test_list_threads_no_filter(
	client: AsyncClient,
	db_session: AsyncSession,
	user_auth: dict[str, object],
) -> None:
	"""Test listing threads without owner filter."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	from api.models.user import User as UserORM

	user_orm = await db_session.get(UserORM, user["id"])
	assert user_orm is not None
	principal = Principal(user=user_orm, group_ids=(), permissions=frozenset())

	thread_in = ThreadCreate(owner_id=user_orm.id, title="Test")
	await thread_service.create_thread(thread_in, db_session, principal=principal)

	# Call service directly without owner_id
	threads = await thread_service.list_threads(db_session, principal=principal)
	assert len(threads) >= 1

	# Call via client without owner_id
	resp = await client.get("/v1/threads", headers=headers)
	assert resp.status_code == 200
	assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_thread_projects(
	db_session: AsyncSession,
) -> None:
	"""Test updating thread projects."""
	from api.models.user import User

	user = User(
		email="svc_update_projects@example.com",
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
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	# Create project
	from api.models.project import Project

	project = Project(name="Test Project", description="Test", owner_id=user.id)
	db_session.add(project)
	await db_session.commit()
	await db_session.refresh(project)

	# Create thread
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user.id, title="Test"),
		db_session,
		principal=principal,
	)

	# Update thread with project
	updated = await thread_service.update_thread(
		thread.id,
		ThreadUpdate(project_ids=[project.id]),
		db_session,
		principal=principal,
	)
	assert len(updated.projects) == 1
	assert updated.projects[0].id == project.id
