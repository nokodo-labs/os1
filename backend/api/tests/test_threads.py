"""Thread-specific tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.project import Project
from api.schemas.thread import ThreadCreate
from api.v1.service import threads as thread_service


@pytest.mark.asyncio
async def test_thread_project_association(
	client: AsyncClient,
	db_session: AsyncSession,
) -> None:
	"""Threads can belong to multiple projects and be reassigned."""
	user_payload = {
		"email": "owner@example.com",
		"username": "owner",
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
	updated = update_resp.json()
	assert updated["project_ids"] == [project_b.id]
	assert len(updated["projects"]) == 1


@pytest.mark.asyncio
async def test_create_thread_basic(client: AsyncClient) -> None:
	"""Test creating a thread without projects."""
	user_payload = {
		"email": "basic@example.com",
		"username": "basic",
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
		"username": "list",
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
		"username": "msg",
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
		"username": "proj",
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
		username="service",
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
			"username": "u1",
			"password": "password",
		},
	)
	user1 = user1_resp.json()

	user2_resp = await client.post(
		"/v1/users",
		json={
			"email": "u2@example.com",
			"username": "u2",
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

	# Create Assistant Message
	asst_msg = {
		"type": "assistant",
		"content": "Hello",
		"sender_agent_id": None,  # Optional
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=asst_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "assistant"

	# Create System Message
	sys_msg = {
		"type": "system",
		"content": "System Prompt",
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=sys_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "system"

	# Create Tool Message
	tool_msg = {
		"type": "tool",
		"content": "Tool Output",
		"tool_calls": [],
	}
	resp = await client.post(f"/v1/threads/{thread_id}/messages", json=tool_msg)
	assert resp.status_code == 201
	assert resp.json()["type"] == "tool"
