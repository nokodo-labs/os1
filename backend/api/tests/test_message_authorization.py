"""message authorization coverage."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.message import AssistantMessage, MessageType, UserMessage
from api.models.thread import Thread
from api.permissions import ResourceType
from api.tests.factories import create_user, principal_for
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	get_effective_access_level,
	level_satisfies,
	require_resource_access,
	resolve_accessible_user_ids,
)
from nokodo_ai.utils.typeid import TypeID


async def _assert_message_access(
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID,
	required_level: AccessLevel,
	expected_level: AccessLevel | None,
) -> None:
	assert (
		await get_effective_access_level(
			session,
			principal,
			ResourceType.MESSAGE,
			message_id,
		)
		== expected_level
	)
	if expected_level is not None and level_satisfies(
		expected_level,
		required_level,
	):
		await require_resource_access(
			message_id,
			session,
			principal,
			ResourceType.MESSAGE,
			required_level=required_level,
		)
		return
	with pytest.raises(HTTPException) as exc:
		await require_resource_access(
			message_id,
			session,
			principal,
			ResourceType.MESSAGE,
			required_level=required_level,
		)
	assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
	("principal_kind", "required_level", "expected_level"),
	[
		("reader", AccessLevel.READER, AccessLevel.READER),
		("outsider", AccessLevel.READER, None),
		("author", AccessLevel.EDITOR, AccessLevel.EDITOR),
		("peer", AccessLevel.EDITOR, AccessLevel.READER),
		("admin", AccessLevel.EDITOR, AccessLevel.ADMIN),
		("author", AccessLevel.ADMIN, AccessLevel.EDITOR),
		("admin", AccessLevel.ADMIN, AccessLevel.ADMIN),
	],
)
async def test_authored_message_access_matrix(
	db_session: AsyncSession,
	principal_kind: str,
	required_level: AccessLevel,
	expected_level: AccessLevel | None,
) -> None:
	owner = await create_user(db_session, f"mmo_{uuid4().hex[:12]}")
	author = await create_user(db_session, f"mma_{uuid4().hex[:12]}")
	reader = await create_user(db_session, f"mmr_{uuid4().hex[:12]}")
	peer = await create_user(db_session, f"mmp_{uuid4().hex[:12]}")
	admin = await create_user(db_session, f"mmx_{uuid4().hex[:12]}")
	outsider = await create_user(db_session, f"mmn_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="authored message matrix")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=author.id,
		content=[{"type": "text", "text": "authored"}],
	)
	db_session.add(message)
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=reader.id,
				level=AccessLevel.READER,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=author.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=peer.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=admin.id,
				level=AccessLevel.ADMIN,
			),
		]
	)
	await db_session.flush()
	principals = {
		"reader": principal_for(reader),
		"outsider": principal_for(outsider),
		"author": principal_for(author),
		"peer": principal_for(peer),
		"admin": principal_for(admin),
	}

	await _assert_message_access(
		db_session,
		principals[principal_kind],
		message.id,
		required_level,
		expected_level,
	)


@pytest.mark.asyncio
async def test_bulk_message_editors_honor_author_gate(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"mbo_{uuid4().hex[:12]}")
	author = await create_user(db_session, f"mba_{uuid4().hex[:12]}")
	peer = await create_user(db_session, f"mbp_{uuid4().hex[:12]}")
	admin = await create_user(db_session, f"mbx_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="bulk authored message")
	db_session.add(thread)
	await db_session.flush()
	message = UserMessage(
		thread_id=thread.id,
		type=MessageType.USER,
		sender_user_id=author.id,
		content=[{"type": "text", "text": "bulk authored"}],
	)
	db_session.add(message)
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=author.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=peer.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=admin.id,
				level=AccessLevel.ADMIN,
			),
		]
	)
	await db_session.flush()

	editors = set(
		await resolve_accessible_user_ids(
			ResourceType.MESSAGE,
			message.id,
			db_session,
			AccessLevel.EDITOR,
		)
	)
	assert author.id in editors
	assert admin.id in editors
	assert peer.id not in editors


@pytest.mark.asyncio
async def test_agent_authored_message_requires_thread_admin_to_edit(
	db_session: AsyncSession,
) -> None:
	owner = await create_user(db_session, f"amo_{uuid4().hex[:12]}")
	editor = await create_user(db_session, f"ame_{uuid4().hex[:12]}")
	admin = await create_user(db_session, f"ama_{uuid4().hex[:12]}")
	thread = Thread(owner_id=owner.id, title="agent authored message")
	db_session.add(thread)
	await db_session.flush()
	message = AssistantMessage(
		thread_id=thread.id,
		type=MessageType.ASSISTANT,
		sender_user_id=None,
		content=[{"type": "text", "text": "agent response"}],
	)
	db_session.add(message)
	db_session.add_all(
		[
			AccessRule(
				thread_id=thread.id,
				subject_user_id=editor.id,
				level=AccessLevel.EDITOR,
			),
			AccessRule(
				thread_id=thread.id,
				subject_user_id=admin.id,
				level=AccessLevel.ADMIN,
			),
		]
	)
	await db_session.flush()

	await _assert_message_access(
		db_session,
		principal_for(editor),
		message.id,
		AccessLevel.EDITOR,
		AccessLevel.READER,
	)
	await _assert_message_access(
		db_session,
		principal_for(admin),
		message.id,
		AccessLevel.EDITOR,
		AccessLevel.ADMIN,
	)


async def _create_api_user(
	client: AsyncClient,
	admin_headers: dict[str, str],
	label: str,
) -> tuple[dict[str, object], dict[str, str]]:
	unique = uuid4().hex[:12]
	email = f"{label}-{unique}@example.com"
	password = "password"
	response = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": f"u_{unique}",
			"password": password,
			"is_superuser": False,
		},
	)
	assert response.status_code == 201
	login = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login.status_code == 200
	return response.json(), {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_other_thread_editor_cannot_patch_or_delete_message(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	admin_headers_value = admin_auth["headers"]
	assert isinstance(admin_headers_value, dict)
	admin_headers: dict[str, str] = {
		str(key): str(value) for key, value in admin_headers_value.items()
	}
	owner, owner_headers = await _create_api_user(
		client,
		admin_headers,
		"message-boundary-owner",
	)
	editor, editor_headers = await _create_api_user(
		client,
		admin_headers,
		"message-boundary-editor",
	)
	thread_response = await client.post(
		"/v1/threads",
		headers=owner_headers,
		json={"owner_id": owner["id"], "title": "message endpoint boundary"},
	)
	assert thread_response.status_code == 201
	thread_id = thread_response.json()["id"]
	grant_response = await client.post(
		f"/v1/threads/{thread_id}/participants",
		headers=owner_headers,
		json={"user_ids": [editor["id"]]},
	)
	assert grant_response.status_code == 201
	accept_response = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{editor['id']}/invite/accept",
		headers=editor_headers,
	)
	assert accept_response.status_code == 200
	message_response = await client.post(
		f"/v1/threads/{thread_id}/messages",
		headers=owner_headers,
		json={"content": "owner message", "type": "user"},
	)
	assert message_response.status_code == 201
	message_id = message_response.json()["id"]

	patch_response = await client.patch(
		f"/v1/threads/{thread_id}/messages/{message_id}",
		headers=editor_headers,
		json={"content": "unauthorized edit"},
	)
	assert patch_response.status_code == 404
	delete_response = await client.delete(
		f"/v1/threads/{thread_id}/messages/{message_id}",
		headers=editor_headers,
	)
	assert delete_response.status_code == 404
	replace_response = await client.post(
		f"/v1/threads/{thread_id}/messages",
		headers=editor_headers,
		json={
			"content": "unauthorized replacement",
			"type": "user",
			"splice": {
				"parent_id": None,
				"replaces": {"head_id": message_id, "tail_id": message_id},
			},
		},
	)
	assert replace_response.status_code == 404
	message_list = await client.get(
		f"/v1/threads/{thread_id}/messages",
		headers=owner_headers,
	)
	assert message_list.status_code == 200
	assert message_id in {message["id"] for message in message_list.json()}
