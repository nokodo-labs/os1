"""End-to-end test covering the first ORM POC."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_async_agentic_flow(client: AsyncClient) -> None:
	"""Exercise the primary architecture entities in a single flow."""
	# Create a baseline user
	user_payload = {
		"email": "poc@example.com",
		"username": "poc-user",
		"password": "supersecret",
		"display_name": "POC User",
	}
	user_resp = await client.post("/v1/users", json=user_payload)
	assert user_resp.status_code == 201
	user = user_resp.json()

	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": user_payload["email"], "password": user_payload["password"]},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	headers = {"Authorization": f"Bearer {token}"}

	# Register a provider → model → agent pipeline
	provider_resp = await client.post(
		"/v1/providers",
		json={
			"name": "openai",
			"adapter_type": "openai_chat_completions",
			"base_url": "https://api.openai.com/v1",
		},
		headers=headers,
	)
	assert provider_resp.status_code == 201
	provider_id = provider_resp.json()["id"]

	model_resp = await client.post(
		"/v1/models",
		json={
			"provider_id": provider_id,
			"name": "gpt-5.1-codex",
			"display_name": "GPT-5.1 Codex",
			"capabilities": ["text", "function_calling"],
		},
		headers=headers,
	)
	assert model_resp.status_code == 201
	model_id = model_resp.json()["id"]

	agent_resp = await client.post(
		"/v1/agents",
		json={
			"name": "nokodo-copilot",
			"system_prompt": "You are nokodo.",
			"model_id": model_id,
			"plugin_ids": [],  # empty list - no plugins assigned
		},
		headers=headers,
	)
	assert agent_resp.status_code == 201

	# Create a thread and append a message
	thread_resp = await client.post(
		"/v1/threads",
		json={
			"owner_id": user["id"],
			"title": "Kickoff",
			"metadata": {"topic": "architecture"},
		},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread = thread_resp.json()

	message_resp = await client.post(
		f"/v1/threads/{thread['id']}/messages",
		json={
			"type": "user",
			"content": "Let's start",
		},
		headers=headers,
	)
	assert message_resp.status_code == 201
	message = message_resp.json()

	list_threads = await client.get(
		f"/v1/threads?owner_id={user['id']}",
		headers=headers,
	)
	assert list_threads.status_code == 200
	assert any(item["id"] == thread["id"] for item in list_threads.json())

	messages_list = await client.get(
		f"/v1/threads/{thread['id']}/messages",
		headers=headers,
	)
	assert messages_list.status_code == 200
	assert len(messages_list.json()) == 1

	# Task lifecycle
	task_resp = await client.post(
		"/v1/tasks",
		json={
			"user_id": user["id"],
			"task_type": "code_session",
			"spawned_thread_id": thread["id"],
		},
		headers=headers,
	)
	assert task_resp.status_code == 201
	task_id = task_resp.json()["id"]

	task_update = await client.patch(
		f"/v1/tasks/{task_id}",
		json={"status": "running", "stage": "analysis"},
		headers=headers,
	)
	assert task_update.status_code == 200
	assert task_update.json()["status"] == "running"

	# Emit an event (events are independent of notifications)
	event_resp = await client.post(
		"/v1/events",
		json={
			"scope": "thread",
			"scope_id": thread["id"],
			"type": "task_progress",
			"user_id": user["id"],
			"thread_id": thread["id"],
			"task_id": task_id,
			"data": {"stage": "analysis"},
		},
		headers=headers,
	)
	assert event_resp.status_code == 201

	# Create a notification via the notifications endpoint (not auto-created by events)
	notif_resp = await client.post(
		"/v1/notifications",
		json={
			"user_ids": [user["id"]],
			"title": "Task Progress",
			"body": "Analysis stage started",
		},
		headers=headers,
	)
	assert notif_resp.status_code == 201

	notifications_resp = await client.get(
		f"/v1/notifications/users/{user['id']}",
		headers=headers,
	)
	assert notifications_resp.status_code == 200
	notifications = notifications_resp.json()
	assert len(notifications) == 1
	notification_id = notifications[0]["id"]

	mark_read = await client.post(
		f"/v1/notifications/{notification_id}/read",
		headers=headers,
	)
	assert mark_read.status_code == 200
	assert mark_read.json()["read_at"] is not None

	# Capture and retrieve memory entries
	memory_resp = await client.post(
		"/v1/memories",
		json={
			"user_id": user["id"],
			"content": "Prefers detailed summaries",
			"source_message_id": message["id"],
		},
		headers=headers,
	)
	assert memory_resp.status_code == 201

	memories = await client.get(f"/v1/memories?user_id={user['id']}", headers=headers)
	assert memories.status_code == 200
	assert len(memories.json()) == 1

	# Catalog endpoints return the configured entities
	agents_list = await client.get("/v1/agents", headers=headers)
	assert agents_list.status_code == 200
	assert len(agents_list.json()) == 1
