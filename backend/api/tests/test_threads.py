"""Thread-specific tests."""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import MessageType
from api.models.project import Project
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.v1.service import threads as thread_service


@pytest.mark.asyncio
async def test_thread_project_association(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Threads can belong to multiple projects and be reassigned."""
	user_payload = {
		"email": "owner@example.com",
		"password": "supersecret",
		"display_name": "Thread Owner",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	assert user_resp.status_code == 201
	user = user_resp.json()

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
	thread_resp = await client.post("/v1/threads", json=thread_payload)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()
	assert set(thread["project_ids"]) == {project_a.id, project_b.id}
	assert len(thread["projects"]) == 2

	update_resp = await client.patch(
		f"/v1/threads/{thread['id']}",
		json={"project_ids": [project_b.id]},
	)
	assert update_resp.status_code == 200
	updated_thread = update_resp.json()
	assert set(updated_thread["project_ids"]) == {project_b.id}


@pytest.mark.asyncio
async def test_create_thread_basic(client: AsyncClient) -> None:
	"""Test creating a thread without projects."""
	user_payload = {
		"email": "basic@example.com",
		"password": "password",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	assert user_resp.status_code == 201
	user = user_resp.json()

	thread_payload = {
		"owner_id": user["id"],
		"title": "Basic Thread",
	}
	thread_resp = await client.post("/v1/threads", json=thread_payload)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()
	assert thread["title"] == "Basic Thread"
	assert thread["owner_id"] == user["id"]
	assert thread["project_ids"] == []


@pytest.mark.asyncio
async def test_list_threads(client: AsyncClient) -> None:
	"""Test listing threads."""
	user_payload = {
		"email": "list@example.com",
		"password": "password",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	user = user_resp.json()

	# Create 2 threads
	await client.post("/v1/threads", json={"owner_id": user["id"], "title": "T1"})
	await client.post("/v1/threads", json={"owner_id": user["id"], "title": "T2"})

	resp = await client.get(f"/v1/threads?owner_id={user['id']}")
	assert resp.status_code == 200
	threads = resp.json()
	assert len(threads) == 2
	titles = {t["title"] for t in threads}
	assert titles == {"T1", "T2"}


@pytest.mark.asyncio
async def test_thread_messages(client: AsyncClient) -> None:
	"""Test creating and listing messages in a thread."""
	user_payload = {
		"email": "msg@example.com",
		"password": "password",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	user = user_resp.json()

	thread_resp = await client.post(
		"/v1/threads", json={"owner_id": user["id"], "title": "Msg Thread"}
	)
	thread_id = thread_resp.json()["id"]

	# Create user message
	msg_payload = {
		"content": "Hello AI",
		"type": "user",
		"sender_user_id": user["id"],
	}
	msg_resp = await client.post(f"/v1/threads/{thread_id}/messages", json=msg_payload)
	assert msg_resp.status_code == 201
	msg = msg_resp.json()
	assert msg["content"] == "Hello AI"
	assert msg["type"] == "user"

	# List messages
	list_resp = await client.get(f"/v1/threads/{thread_id}/messages")
	assert list_resp.status_code == 200
	messages = list_resp.json()
	assert len(messages) == 1
	assert messages[0]["id"] == msg["id"]


@pytest.mark.asyncio
async def test_create_thread_invalid_user(client: AsyncClient) -> None:
	"""Test creating a thread with non-existent user."""
	thread_payload = {
		"owner_id": 99999,
		"title": "Invalid User Thread",
	}
	resp = await client.post("/v1/threads", json=thread_payload)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_create_thread_invalid_project(client: AsyncClient) -> None:
	"""Test creating a thread with non-existent project."""
	user_payload = {
		"email": "proj@example.com",
		"password": "password",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	user = user_resp.json()

	thread_payload = {
		"owner_id": user["id"],
		"title": "Invalid Project Thread",
		"project_ids": ["non-existent-id"],
	}
	resp = await client.post("/v1/threads", json=thread_payload)
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

	thread_in = ThreadCreate(
		owner_id=user.id,
		title="Service Thread",
	)
	thread = await thread_service.create_thread(thread_in, db_session)
	assert thread.title == "Service Thread"
	assert thread.owner_id == user.id


@pytest.mark.asyncio
async def test_get_thread_not_found(client: AsyncClient) -> None:
	"""Test getting a non-existent thread."""
	resp = await client.get("/v1/threads/00000000-0000-0000-0000-000000000000")
	assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_thread_owner(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Test updating thread owner."""
	# Create two users
	user1_resp = await client.post(
		"/v1/users",
		json={
			"email": "u1@example.com",
			"password": "password",
		},
	)
	user1 = user1_resp.json()

	user2_resp = await client.post(
		"/v1/users",
		json={
			"email": "u2@example.com",
			"password": "password",
		},
	)
	user2 = user2_resp.json()

	# Create thread with user1
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user1["id"], "title": "Owner Update"},
	)
	thread_id = thread_resp.json()["id"]

	# Update owner to user2
	update_resp = await client.patch(
		f"/v1/threads/{thread_id}",
		json={"owner_id": user2["id"]},
	)
	assert update_resp.status_code == 200
	updated = update_resp.json()
	assert updated["owner_id"] == user2["id"]


@pytest.mark.asyncio
async def test_create_message_types(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Test creating different message types."""
	# Create user and thread
	user_resp = await client.post(
		"/v1/users",
		json={
			"email": "msg@example.com",
			"username": "msg",
			"password": "password",
		},
	)
	user = user_resp.json()
	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "Message Types"},
	)
	thread_id = thread_resp.json()["id"]

	# Assistant Message
	asst_msg = {
		"type": "assistant",
		"content": "Hello",
		"sender_agent_id": None,  # Optional
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=asst_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "assistant"

	# System Message
	sys_msg = {
		"type": "system",
		"content": "System Prompt",
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=sys_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "system"

	# Tool Message
	tool_msg = {
		"type": "tool",
		"content": "Tool Output",
		"tool_calls": [],
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=tool_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "tool"


@pytest.mark.asyncio
async def test_get_thread_not_found_service(db_session: AsyncSession) -> None:
	with pytest.raises(HTTPException) as exc:
		await thread_service.get_thread("nonexistent", db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_invalid_user_service(db_session: AsyncSession) -> None:
	thread_in = ThreadCreate(owner_id=99999, title="Test")
	with pytest.raises(HTTPException) as exc:
		await thread_service.create_thread(thread_in, db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_thread_invalid_project_service(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	# Create a user first
	user_payload = {"email": "p@example.com", "username": "p", "password": "p"}
	user_resp = await client.post("/v1/users", json=user_payload)
	user_id = user_resp.json()["id"]

	thread_in = ThreadCreate(owner_id=user_id, title="Test", project_ids=["bad-id"])
	with pytest.raises(HTTPException) as exc:
		await thread_service.create_thread(thread_in, db_session)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_threads_filter_owner(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	# Create user and thread
	user_payload = {"email": "l@example.com", "username": "l", "password": "l"}
	user_resp = await client.post("/v1/users", json=user_payload)
	user_id = user_resp.json()["id"]

	thread_in = ThreadCreate(owner_id=user_id, title="Test")
	await thread_service.create_thread(thread_in, db_session)

	threads = await thread_service.list_threads(db_session, owner_id=user_id)
	assert len(threads) == 1
	assert threads[0].owner_id == user_id

	threads_empty = await thread_service.list_threads(db_session, owner_id=99999)
	assert len(threads_empty) == 0


@pytest.mark.asyncio
async def test_update_thread_owner_service(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	# Create two users
	u1_resp = await client.post(
		"/v1/users", json={"email": "u1@e.com", "username": "u1", "password": "p"}
	)
	u1_id = u1_resp.json()["id"]
	u2_resp = await client.post(
		"/v1/users", json={"email": "u2@e.com", "username": "u2", "password": "p"}
	)
	u2_id = u2_resp.json()["id"]

	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=u1_id, title="T"), db_session
	)

	updated = await thread_service.update_thread(
		thread.id, ThreadUpdate(owner_id=u2_id), db_session
	)
	assert updated.owner_id == u2_id


@pytest.mark.asyncio
async def test_create_message_types_service(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	u_resp = await client.post(
		"/v1/users", json={"email": "m@e.com", "username": "m", "password": "p"}
	)
	u_id = u_resp.json()["id"]
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=u_id, title="T"), db_session
	)

	# Assistant
	msg_asst = await thread_service.create_message(
		thread.id,
		MessageCreate(content="A", type=MessageType.ASSISTANT, sender_user_id=u_id),
		db_session,
	)
	assert msg_asst.type == MessageType.ASSISTANT

	# Tool
	msg_tool = await thread_service.create_message(
		thread.id,
		MessageCreate(content="T", type=MessageType.TOOL, sender_user_id=u_id),
		db_session,
	)
	assert msg_tool.type == MessageType.TOOL

	# System
	msg_sys = await thread_service.create_message(
		thread.id,
		MessageCreate(content="S", type=MessageType.SYSTEM, sender_user_id=u_id),
		db_session,
	)
	assert msg_sys.type == MessageType.SYSTEM


@pytest.mark.asyncio
async def test_create_message_unknown_type_service(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	"""Ensure unexpected message types fall back to user messages."""
	u_resp = await client.post(
		"/v1/users", json={"email": "unk@e.com", "username": "unk", "password": "p"}
	)
	u_id = u_resp.json()["id"]
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=u_id, title="Unknown"), db_session
	)
	message_in = MessageCreate.model_construct(
		content="Fallback",
		sender_user_id=u_id,
		type=cast(Any, "custom"),
	)
	message = await thread_service.create_message(thread.id, message_in, db_session)
	assert message.type == MessageType.USER


@pytest.mark.asyncio
async def test_list_messages_service(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	u_resp = await client.post(
		"/v1/users", json={"email": "lm@e.com", "username": "lm", "password": "p"}
	)
	u_id = u_resp.json()["id"]
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=u_id, title="T"), db_session
	)

	await thread_service.create_message(
		thread.id, MessageCreate(content="1", sender_user_id=u_id), db_session
	)
	await thread_service.create_message(
		thread.id, MessageCreate(content="2", sender_user_id=u_id), db_session
	)

	msgs = await thread_service.list_messages(thread.id, db_session)
	assert len(msgs) == 2


@pytest.mark.asyncio
async def test_list_threads_no_filter(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	"""Test listing threads without owner filter."""
	# Create user and thread
	user_payload = {"email": "nf@example.com", "username": "nf", "password": "p"}
	user_resp = await client.post("/v1/users", json=user_payload)
	user_id = user_resp.json()["id"]

	thread_in = ThreadCreate(owner_id=user_id, title="Test")
	await thread_service.create_thread(thread_in, db_session)

	# Call service directly without owner_id
	threads = await thread_service.list_threads(db_session)
	assert len(threads) >= 1

	# Call via client without owner_id
	resp = await client.get("/v1/threads")
	assert resp.status_code == 200
	assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_thread_projects(
	client: AsyncClient, db_session: AsyncSession
) -> None:
	"""Test updating thread projects."""
	# Create user
	user_payload = {"email": "up@example.com", "username": "up", "password": "p"}
	user_resp = await client.post("/v1/users", json=user_payload)
	user_id = user_resp.json()["id"]

	# Create project
	from api.models.project import Project

	project = Project(name="Test Project", description="Test", owner_id=user_id)
	db_session.add(project)
	await db_session.commit()
	await db_session.refresh(project)

	# Create thread
	thread = await thread_service.create_thread(
		ThreadCreate(owner_id=user_id, title="Test"), db_session
	)

	# Update thread with project
	updated = await thread_service.update_thread(
		thread.id, ThreadUpdate(project_ids=[project.id]), db_session
	)
	assert len(updated.projects) == 1
	assert updated.projects[0].id == project.id
