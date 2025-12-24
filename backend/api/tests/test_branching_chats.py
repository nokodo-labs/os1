"""Branching chat (message tree) API tests."""

from __future__ import annotations

from typing import Any, cast

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import MessageCreate
from api.v1.service import threads as thread_service
from api.v1.service.auth import Principal
from nokodo_ai.utils.typeid import TypeID, new_typeid


@pytest.mark.asyncio
async def test_branching_chat_endpoints_support_forks(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "branch thread"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	# empty chats return an empty branch
	empty_branch = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert empty_branch.status_code == 200
	assert empty_branch.json() == []

	# root user message
	m1_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "hello", "type": "user", "sender_user_id": user["id"]},
		headers=headers,
	)
	assert m1_resp.status_code == 201
	m1 = m1_resp.json()
	assert m1["parent_id"] is None

	# single-node branch (current leaf is the root)
	root_branch = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert root_branch.status_code == 200
	assert [m["id"] for m in root_branch.json()] == [m1["id"]]

	# assistant reply (defaults to parent=current head)
	m2_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "hi there", "type": "assistant"},
		headers=headers,
	)
	assert m2_resp.status_code == 201
	m2 = m2_resp.json()
	assert m2["parent_id"] == m1["id"]

	# fork: alternate assistant reply from the same parent
	m3_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "alt reply", "type": "assistant", "parent_id": m1["id"]},
		headers=headers,
	)
	assert m3_resp.status_code == 201
	m3 = m3_resp.json()
	assert m3["parent_id"] == m1["id"]

	# current branch should follow the latest leaf (m3)
	branch_resp = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert branch_resp.status_code == 200
	branch = branch_resp.json()
	assert [m["id"] for m in branch] == [m1["id"], m3["id"]]

	# append to current leaf without specifying parent_id
	m4_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "follow-up", "type": "user", "sender_user_id": user["id"]},
		headers=headers,
	)
	assert m4_resp.status_code == 201
	m4 = m4_resp.json()
	assert m4["parent_id"] == m3["id"]

	branch_resp = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	branch = branch_resp.json()
	assert [m["id"] for m in branch] == [m1["id"], m3["id"], m4["id"]]

	# tree should include all messages
	tree_resp = await client.get(f"/v1/threads/{thread_id}/tree", headers=headers)
	assert tree_resp.status_code == 200
	tree = tree_resp.json()
	assert {m["id"] for m in tree} == {m1["id"], m2["id"], m3["id"], m4["id"]}

	# switch to the other branch (m2)
	switch_resp = await client.post(
		f"/v1/threads/{thread_id}/switch",
		json={"message_id": m2["id"]},
		headers=headers,
	)
	assert switch_resp.status_code == 200
	payload = switch_resp.json()
	assert payload["ok"] is True
	assert payload["current_message_id"] == m2["id"]

	branch_resp = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert [m["id"] for m in branch_resp.json()] == [m1["id"], m2["id"]]

	# switching to the root should pick the deepest leaf in its subtree
	deep_switch = await client.post(
		f"/v1/threads/{thread_id}/switch",
		json={"message_id": m1["id"]},
		headers=headers,
	)
	assert deep_switch.status_code == 200
	assert deep_switch.json()["current_message_id"] == m4["id"]


@pytest.mark.asyncio
async def test_chat_switch_rejects_unknown_message(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "switch thread"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	resp = await client.post(
		f"/v1/threads/{thread_id}/switch",
		json={"message_id": new_typeid("msg")},
		headers=headers,
	)
	assert resp.status_code == 404
	assert resp.json()["detail"] == "Message not found"


@pytest.mark.asyncio
async def test_chat_rejects_invalid_parent_id_and_cross_thread_switch(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_a = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "a"},
		headers=headers,
	)
	thread_b = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "b"},
		headers=headers,
	)
	thread_a_id = thread_a.json()["id"]
	thread_b_id = thread_b.json()["id"]

	# invalid parent id should 404
	invalid_parent = await client.post(
		f"/v1/threads/{thread_a_id}/messages",
		json={
			"content": "orphan",
			"type": "user",
			"sender_user_id": user["id"],
			"parent_id": new_typeid("msg"),
		},
		headers=headers,
	)
	assert invalid_parent.status_code == 404
	assert invalid_parent.json()["detail"] == "Parent message not found"

	# create a message in chat_b
	b_msg_resp = await client.post(
		f"/v1/threads/{thread_b_id}/messages",
		json={"content": "hello", "type": "user", "sender_user_id": user["id"]},
		headers=headers,
	)
	assert b_msg_resp.status_code == 201
	b_msg = b_msg_resp.json()

	# switching chat_a to a message from chat_b should 404
	cross_switch = await client.post(
		f"/v1/threads/{thread_a_id}/switch",
		json={"message_id": b_msg["id"]},
		headers=headers,
	)
	assert cross_switch.status_code == 404
	assert cross_switch.json()["detail"] == "Message not found"


@pytest.mark.asyncio
async def test_get_current_branch_handles_missing_current_message_gracefully(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	user = User(
		email="branch-miss@example.com",
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
	user_id = cast(TypeID, user.id)
	principal = Principal(user=user, group_ids=(), permissions=frozenset())

	thread = Thread(owner_id=user_id, title="branch miss")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)
	thread_id = cast(TypeID, thread.id)

	msg = await thread_service.create_message(
		thread_id,
		MessageCreate(
			content="hello",
			type=MessageType.USER,
			sender_user_id=user_id,
		),
		db_session,
		principal=principal,
	)
	assert thread.current_message_id == msg.id

	original_get = db_session.get

	async def fake_get(entity: Any, ident: Any, **kwargs: Any) -> Any:
		if entity is Message and ident == thread.current_message_id:
			return None
		return await original_get(entity, ident, **kwargs)

	monkeypatch.setattr(db_session, "get", fake_get)
	branch = await thread_service.get_current_branch(
		thread_id,
		db_session,
		principal=principal,
	)
	assert branch == []
