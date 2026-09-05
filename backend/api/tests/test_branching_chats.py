"""Branching chat (message tree) API tests."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.message import MessageType
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import TextContent
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.utils.typeid import new_typeid


@pytest.mark.asyncio
async def test_branching_chat_endpoints_support_forks(
	client: AsyncClient,
	user_auth: dict[str, object],
	admin_auth: dict[str, object],
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

	async def _branch_ids(tid: str) -> list[str]:
		resp = await client.get(f"/v1/threads/{tid}/branch", headers=headers)
		assert resp.status_code == 200
		return [m["id"] for m in resp.json()["messages"]]

	# empty chats return an empty branch page
	empty_branch = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert empty_branch.status_code == 200
	assert empty_branch.json()["messages"] == []
	assert empty_branch.json()["total"] == 0

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
	assert await _branch_ids(thread_id) == [m1["id"]]

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
		json={
			"content": "alt reply",
			"type": "assistant",
			"splice": {"parent_id": m1["id"]},
		},
		headers=headers,
	)
	assert m3_resp.status_code == 201
	m3 = m3_resp.json()
	assert m3["parent_id"] == m1["id"]

	# current branch should follow the latest leaf (m3)
	assert await _branch_ids(thread_id) == [m1["id"], m3["id"]]

	# append to current leaf without specifying parent_id
	m4_resp = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "follow-up", "type": "user", "sender_user_id": user["id"]},
		headers=headers,
	)
	assert m4_resp.status_code == 201
	m4 = m4_resp.json()
	assert m4["parent_id"] == m3["id"]

	assert await _branch_ids(thread_id) == [m1["id"], m3["id"], m4["id"]]

	# /tree is operator-only
	tree_resp = await client.get(f"/v1/threads/{thread_id}/tree", headers=headers)
	assert tree_resp.status_code == 403
	admin_headers = admin_auth["headers"]
	assert isinstance(admin_headers, dict)
	tree_resp = await client.get(f"/v1/threads/{thread_id}/tree", headers=admin_headers)
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

	assert await _branch_ids(thread_id) == [m1["id"], m2["id"]]

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
	assert resp.json()["detail"] == "message not found"


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
			"splice": {"parent_id": new_typeid("msg")},
		},
		headers=headers,
	)
	assert invalid_parent.status_code == 404
	assert invalid_parent.json()["detail"] == "parent message not found in this thread"

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
	assert cross_switch.json()["detail"] == "message not found"


@pytest.mark.asyncio
async def test_get_current_branch_handles_missing_current_message_gracefully(
	db_session: AsyncSession,
) -> None:
	user = User(
		email="branch-miss@example.com",
		username="branch_miss",
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
	user_id = user.id
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = Thread(owner_id=user_id, title="branch miss")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)
	thread_id = thread.id

	msg = await thread_service.create_message(
		thread_id,
		MessageDraft(
			content=[TextContent(text="hello")],
			type=MessageType.USER,
			sender_user_id=user_id,
		),
		db_session,
		principal=principal,
	)
	assert thread.current_message_id == msg.message.id

	# clear current_message_id to simulate no head pointer
	thread.current_message_id = None
	await db_session.commit()

	branch = await thread_service.get_current_branch(
		thread_id,
		db_session,
		principal=principal,
	)
	assert branch == []


@pytest.mark.asyncio
async def test_get_branch_page_windows_in_sql(
	db_session: AsyncSession,
) -> None:
	"""paging, anchor snapping, and before/after windows on the branch CTE."""
	user = User(
		email="branch-page@example.com",
		username="branch_page",
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
	user_id = user.id
	principal = Principal.for_user(user=user, group_ids=(), permissions=frozenset())

	thread = Thread(owner_id=user_id, title="branch page")
	db_session.add(thread)
	await db_session.commit()
	await db_session.refresh(thread)
	thread_id = thread.id

	messages = []
	for index in range(7):
		messages.append(
			(
				await thread_service.create_message(
					thread_id,
					MessageDraft(
						content=[TextContent(text=f"message {index}")],
						type=MessageType.USER,
						sender_user_id=user_id,
					),
					db_session,
					principal=principal,
				)
			).message
		)

	# newest page: depths 0-2 = the last three messages, root-first
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		skip=0,
		limit=3,
	)
	assert page.total == 7
	assert page.skip == 0
	assert [m.id for m in page.messages] == [m.id for m in messages[4:]]
	assert page.has_toward_root
	assert not page.has_toward_leaf

	# skip walks toward the root
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		skip=3,
		limit=3,
	)
	assert page.skip == 3
	assert [m.id for m in page.messages] == [m.id for m in messages[1:4]]
	assert page.has_toward_root
	assert page.has_toward_leaf

	# anchor without window snaps to the page containing it
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		limit=3,
		anchor_message_id=messages[2].id,
	)
	assert page.skip == 3
	assert [m.id for m in page.messages] == [m.id for m in messages[1:4]]

	# anchor with before/after returns the exact window
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		anchor_message_id=messages[3].id,
		before=1,
		after=2,
	)
	assert [m.id for m in page.messages] == [m.id for m in messages[2:6]]
	assert page.skip == 1

	# unknown anchor raises 404
	with pytest.raises(HTTPException) as excinfo:
		await thread_service.get_branch_page(
			thread_id,
			db_session,
			principal=principal,
			anchor_message_id=new_typeid("msg"),
		)
	assert excinfo.value.status_code == 404
