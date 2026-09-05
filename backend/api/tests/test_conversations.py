"""tests for messaging via the unified thread creation path (DMs, groups, invites).

a thread's nature is emergent from who is in it, so DMs and groups are created
through the same ``POST /v1/threads`` endpoint - a DM is one member, a group is
several. there are no dedicated /dm or /group endpoints.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from api.database.main import async_session_local
from api.schemas.thread import ThreadCreate
from api.v1.service import threads as thread_service
from api.v1.service.authentication import load_principal_for_user
from nokodo_ai.utils.typeid import TypeID


def _headers(auth: dict[str, object]) -> dict[str, str]:
	"""narrow an auth fixture's headers to a string mapping."""
	headers = auth["headers"]
	assert isinstance(headers, dict)
	return {str(k): str(v) for k, v in headers.items()}


async def _make_user(
	client: AsyncClient, admin_headers: dict[str, str]
) -> dict[str, Any]:
	"""create a fresh non-admin user and return its auth context."""
	uniq = uuid4().hex[:10]
	email = f"conv{uniq}@example.com"
	username = f"conv{uniq}"
	password = "password"
	user_resp = await client.post(
		"/v1/users",
		headers=admin_headers,
		json={
			"email": email,
			"username": username,
			"password": password,
			"is_superuser": False,
		},
	)
	assert user_resp.status_code == 201
	user = user_resp.json()
	login_resp = await client.post(
		"/v1/auth/login/access-token",
		data={"username": email, "password": password},
	)
	assert login_resp.status_code == 200
	token = login_resp.json()["access_token"]
	return {"user": user, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_thread(
	client: AsyncClient, actor: dict[str, Any], **body: Any
) -> dict[str, Any]:
	"""create a thread as actor; owner_id defaults to the actor."""
	payload = {"owner_id": actor["user"]["id"], **body}
	resp = await client.post("/v1/threads", headers=actor["headers"], json=payload)
	assert resp.status_code == 201, resp.text
	return resp.json()


async def _befriend(client: AsyncClient, a: dict[str, Any], b: dict[str, Any]) -> None:
	"""accept a friendship between two users.

	membership is friend-gated: a friend joins as an editor, a stranger only
	gets a read-only invite - and readers never make a thread a people
	conversation.
	"""
	request = await client.post(
		f"/v1/users/{a['user']['id']}/friends/requests",
		headers=_headers(a),
		json={"addressee_id": b["user"]["id"]},
	)
	assert request.status_code == 201, request.text
	accept = await client.post(
		f"/v1/users/{b['user']['id']}/friends/requests/{request.json()['id']}/accept",
		headers=_headers(b),
	)
	assert accept.status_code == 200, accept.text


@pytest.mark.asyncio
async def test_dm_create_is_deduplicated(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""creating a 1:1 thread with the same target twice reuses the same thread."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	first = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	second = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	assert first["id"] == second["id"]


@pytest.mark.asyncio
async def test_concurrent_first_dm_creates_single_thread(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""racing first-time DM creations serialize on the pair lock: one thread.

	runs at the service layer with two independent sessions (real transactions)
	because the advisory lock is transaction-scoped - the http test client
	shares one session and cannot express this race.
	"""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	a_id = TypeID(a["user"]["id"])
	b_id = TypeID(b["user"]["id"])

	async def _create() -> str:
		async with async_session_local() as session:
			principal = await load_principal_for_user(a_id, session)
			thread = await thread_service.create_thread(
				ThreadCreate(owner_id=a_id, member_user_ids=[b_id]),
				session,
				principal=principal,
			)
			return str(thread.id)

	first, second = await asyncio.gather(_create(), _create())
	assert first == second


@pytest.mark.asyncio
async def test_self_membership_yields_solo_thread(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""listing yourself as a member is a no-op: the result is a solo thread."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	thread = await _create_thread(client, a, member_user_ids=[a["user"]["id"]])
	people = await client.get(
		"/v1/threads?participant_scope=people", headers=a["headers"]
	)
	assert thread["id"] not in {t["id"] for t in people.json()}


@pytest.mark.asyncio
async def test_participant_scope_splits_solo_and_people(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""solo chats and people conversations are listed under distinct scopes."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	await _befriend(client, a, b)

	solo = await _create_thread(client, a, title="solo")
	solo_id = solo["id"]
	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	dm_id = dm["id"]

	people = await client.get(
		"/v1/threads?participant_scope=people", headers=a["headers"]
	)
	people_ids = {t["id"] for t in people.json()}
	assert dm_id in people_ids
	assert solo_id not in people_ids

	solo_list = await client.get(
		"/v1/threads?participant_scope=solo", headers=a["headers"]
	)
	solo_ids = {t["id"] for t in solo_list.json()}
	assert solo_id in solo_ids
	assert dm_id not in solo_ids


@pytest.mark.asyncio
async def test_dm_embeds_participants_with_identity(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""the thread payload embeds both humans with their nested identity."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	# participants are a discriminated union on `kind`; humans carry nested user.
	by_user = {p["user"]["id"]: p for p in dm["participants"] if p["kind"] == "user"}
	assert set(by_user) == {a["user"]["id"], b["user"]["id"]}
	# nested user identity is present for rendering without extra lookups.
	assert by_user[b["user"]["id"]]["user"]["username"] == b["user"]["username"]


@pytest.mark.asyncio
async def test_participant_routes_add_and_remove_users(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	admin_headers = _headers(admin_auth)
	owner = await _make_user(client, admin_headers)
	member = await _make_user(client, admin_headers)
	thread = await _create_thread(client, owner, title="participant routes")
	thread_id = thread["id"]
	member_id = member["user"]["id"]

	added = await client.post(
		f"/v1/threads/{thread_id}/participants",
		headers=owner["headers"],
		json={"user_ids": [member_id]},
	)
	assert added.status_code == 201
	assert [(item["kind"], item["id"]) for item in added.json()] == [
		("user", member_id)
	]

	denied = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{member_id}/invite/accept",
		headers=owner["headers"],
	)
	assert denied.status_code == 403

	accepted = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{member_id}/invite/accept",
		headers=member["headers"],
	)
	assert accepted.status_code == 200

	removed = await client.delete(
		f"/v1/threads/{thread_id}/participants/users/{member_id}",
		headers=owner["headers"],
	)
	assert removed.status_code == 204
	assert (
		await client.get(f"/v1/threads/{thread_id}", headers=member["headers"])
	).status_code == 404


@pytest.mark.asyncio
async def test_non_friend_dm_lands_in_invites_then_accept(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""a non-friend target sees an invite and joins on accept."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	dm_id = dm["id"]

	b_id = b["user"]["id"]
	# pending requests are a state filter, not a dedicated endpoint.
	invites = await client.get(
		f"/v1/threads?invite_pending_for={b_id}", headers=b["headers"]
	)
	assert dm_id in {t["id"] for t in invites.json()}
	# the default listing is pure (access only): the pending thread appears.
	listed = await client.get("/v1/threads", headers=b["headers"])
	assert dm_id in {t["id"] for t in listed.json()}
	# a pending invite is read-only, and readers are spectators: the thread is
	# a solo chat for both sides until it is accepted.
	people = await client.get(
		"/v1/threads?participant_scope=people", headers=b["headers"]
	)
	assert dm_id not in {t["id"] for t in people.json()}
	# the inbox view excludes it explicitly.
	inbox = await client.get(
		f"/v1/threads?participant_scope=people&not_invite_pending_for={b_id}",
		headers=b["headers"],
	)
	assert dm_id not in {t["id"] for t in inbox.json()}

	accept = await client.post(
		f"/v1/threads/{dm_id}/participants/users/{b_id}/invite/accept",
		headers=b["headers"],
	)
	assert accept.status_code == 200

	invites_after = await client.get(
		f"/v1/threads?invite_pending_for={b_id}", headers=b["headers"]
	)
	assert dm_id not in {t["id"] for t in invites_after.json()}
	inbox_after = await client.get(
		f"/v1/threads?participant_scope=people&not_invite_pending_for={b_id}",
		headers=b["headers"],
	)
	assert dm_id in {t["id"] for t in inbox_after.json()}


@pytest.mark.asyncio
async def test_accept_without_pending_invite_cannot_escalate(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""a plain reader share cannot self-upgrade to editor via invite accept."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	solo = await _create_thread(client, a, title="read-only share")
	thread_id = solo["id"]
	b_id = b["user"]["id"]

	# raw public ACL remains available for advanced access policy and creates no
	# user-specific invite marker.
	acl = await client.post(
		f"/v1/threads/{thread_id}/access/rules",
		headers=a["headers"],
		json={"level": "reader"},
	)
	assert acl.status_code == 201

	# reading creates b's state row without any pending invite status.
	read = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{b_id}/read",
		headers=b["headers"],
	)
	assert read.status_code == 200

	# accept must refuse: a state row alone is not an invite.
	accept = await client.post(
		f"/v1/threads/{thread_id}/participants/users/{b_id}/invite/accept",
		headers=b["headers"],
	)
	assert accept.status_code == 404

	# b can still read but must not have gained editor rights. writes below
	# editor level are masked as 404 (denials do not reveal existence).
	fetch = await client.get(f"/v1/threads/{thread_id}", headers=b["headers"])
	assert fetch.status_code == 200
	post = await client.post(
		f"/v1/threads/{thread_id}/messages",
		headers=b["headers"],
		json={"content": "should be forbidden"},
	)
	assert post.status_code == 404


@pytest.mark.asyncio
async def test_thread_members_can_read_full_acl(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""any thread member (reader+) sees the full rule list; outsiders see 404.

	rules ARE the membership source of truth for conversations, so members
	must be able to see who is in their chat - including admin entries.
	mutation stays admin-only.
	"""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	c = await _make_user(client, admin_headers)
	d = await _make_user(client, admin_headers)

	thread = await _create_thread(client, a, title="acl visibility")
	thread_id = thread["id"]
	b_id = b["user"]["id"]

	added = await client.post(
		f"/v1/threads/{thread_id}/participants",
		headers=a["headers"],
		json={"user_ids": [b_id, c["user"]["id"]]},
	)
	assert added.status_code == 201

	# the mere reader sees the full list.
	listed = await client.get(
		f"/v1/threads/{thread_id}/access/rules", headers=b["headers"]
	)
	assert listed.status_code == 200
	assert {r["subject_user_id"] for r in listed.json()} == {
		b_id,
		c["user"]["id"],
	}

	# but cannot mutate it.
	denied = await client.post(
		f"/v1/threads/{thread_id}/participants",
		headers=b["headers"],
		json={"user_ids": [d["user"]["id"]]},
	)
	assert denied.status_code == 404
	create_denied = await client.post(
		f"/v1/threads/{thread_id}/access/rules",
		headers=b["headers"],
		json={"subject_user_id": d["user"]["id"], "level": "reader"},
	)
	assert create_denied.status_code in {404, 422}

	# an outsider cannot read the list at all.
	outsider = await client.get(
		f"/v1/threads/{thread_id}/access/rules", headers=d["headers"]
	)
	assert outsider.status_code == 404


@pytest.mark.asyncio
async def test_decline_invite_drops_access(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""declining an invite removes the thread from the user's access."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	dm_id = dm["id"]

	decline = await client.post(
		f"/v1/threads/{dm_id}/participants/users/{b['user']['id']}/invite/decline",
		headers=b["headers"],
	)
	assert decline.status_code == 204
	invites = await client.get(
		f"/v1/threads?invite_pending_for={b['user']['id']}", headers=b["headers"]
	)
	assert dm_id not in {t["id"] for t in invites.json()}
	fetch = await client.get(f"/v1/threads/{dm_id}", headers=b["headers"])
	assert fetch.status_code == 404


@pytest.mark.asyncio
async def test_create_group_lists_for_all_members(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""a group conversation is created with the owner and members."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	c = await _make_user(client, admin_headers)
	# c joins as an editor; b, a stranger, only gets a read-only invite.
	await _befriend(client, a, c)

	group = await _create_thread(
		client,
		a,
		title="squad",
		member_user_ids=[b["user"]["id"], c["user"]["id"]],
	)
	group_id = group["id"]

	# the second writer is what makes it a people conversation.
	people = await client.get(
		"/v1/threads?participant_scope=people", headers=a["headers"]
	)
	assert group_id in {t["id"] for t in people.json()}

	invites = await client.get(
		f"/v1/threads?invite_pending_for={b['user']['id']}", headers=b["headers"]
	)
	assert group_id in {t["id"] for t in invites.json()}


@pytest.mark.asyncio
async def test_group_shared_members_receive_message_notifications(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""acl-driven fanout: group members are notified before ever opening the thread."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	b_id = b["user"]["id"]

	# a group containing b, owned by a.
	group_resp = await client.post(
		"/v1/groups", headers=a["headers"], json={"name": "notify-squad"}
	)
	assert group_resp.status_code == 201
	group_id = group_resp.json()["id"]
	member_resp = await client.post(
		f"/v1/groups/{group_id}/members",
		headers=a["headers"],
		json={"user_id": b_id},
	)
	assert member_resp.status_code == 201

	# a thread shared live with the group; b never touches it.
	thread = await _create_thread(client, a, title="group ping", group_ids=[group_id])
	posted = await client.post(
		f"/v1/threads/{thread['id']}/messages",
		headers=a["headers"],
		json={"content": "hello group", "type": "user"},
	)
	assert posted.status_code == 201

	# the durable notification lands for b (delivery is a background task).
	for _ in range(20):
		notif_resp = await client.get(
			f"/v1/notifications/users/{b_id}", headers=b["headers"]
		)
		assert notif_resp.status_code == 200
		if any(
			(n.get("data") or {}).get("thread_id") == thread["id"]
			for n in notif_resp.json()
		):
			break
		await asyncio.sleep(0.1)
	else:
		raise AssertionError("group member never received a message notification")


@pytest.mark.asyncio
async def test_fork_in_shared_thread_becomes_a_sub_thread(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""a non-head parent starts a sub-thread and leaves canon untouched."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	dm_id = dm["id"]
	# accept -> b becomes an editor -> two writers
	accepted = await client.post(
		f"/v1/threads/{dm_id}/participants/users/{b['user']['id']}/invite/accept",
		headers=b["headers"],
	)
	assert accepted.status_code == 200

	first = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={"content": "hello", "type": "user"},
	)
	assert first.status_code == 201
	first_id = first.json()["id"]

	second = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={"content": "again", "type": "user"},
	)
	assert second.status_code == 201
	head_id = second.json()["id"]

	# replying to an older message opens a sub-thread anchored there.
	sub_root = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=b["headers"],
		json={
			"content": "re: hello",
			"type": "user",
			"splice": {"parent_id": first_id},
		},
	)
	assert sub_root.status_code == 201, sub_root.text
	sub_root_id = sub_root.json()["id"]

	# canon did not move to the sub-thread message.
	thread_resp = await client.get(f"/v1/threads/{dm_id}", headers=a["headers"])
	assert thread_resp.status_code == 200
	assert thread_resp.json()["current_message_id"] != sub_root_id

	branch = await client.get(f"/v1/threads/{dm_id}/branch", headers=a["headers"])
	assert branch.status_code == 200
	branch_ids = [m["id"] for m in branch.json()["messages"]]
	assert sub_root_id not in branch_ids
	assert head_id in branch_ids

	# an off-canon anchor pages the sub-thread chain containing it.
	sub_page = await client.get(
		f"/v1/threads/{dm_id}/branch",
		headers=b["headers"],
		params={"anchor_message_id": sub_root_id},
	)
	assert sub_page.status_code == 200
	sub_ids = [m["id"] for m in sub_page.json()["messages"]]
	assert sub_root_id in sub_ids
	assert head_id not in sub_ids

	# sub-thread replies extend the chain at its leaf.
	nested = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={
			"content": "good point",
			"type": "user",
			"splice": {"parent_id": sub_root_id},
		},
	)
	assert nested.status_code == 201, nested.text
	assert nested.json()["parent_id"] == sub_root_id

	# a second sub-thread on the same anchor is refused in v1.
	dupe = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={
			"content": "another take",
			"type": "user",
			"splice": {"parent_id": first_id},
		},
	)
	assert dupe.status_code == 409


@pytest.mark.asyncio
async def test_canon_switch_in_shared_thread_needs_threads_manage(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""moving shared canon is an operator action; a plain editor cannot."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)

	dm = await _create_thread(client, a, member_user_ids=[b["user"]["id"]])
	dm_id = dm["id"]
	accepted = await client.post(
		f"/v1/threads/{dm_id}/participants/users/{b['user']['id']}/invite/accept",
		headers=b["headers"],
	)
	assert accepted.status_code == 200

	first = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={"content": "hello", "type": "user"},
	)
	assert first.status_code == 201
	first_id = first.json()["id"]
	second = await client.post(
		f"/v1/threads/{dm_id}/messages",
		headers=a["headers"],
		json={"content": "again", "type": "user"},
	)
	assert second.status_code == 201

	denied = await client.post(
		f"/v1/threads/{dm_id}/switch",
		headers=a["headers"],
		json={"message_id": first_id},
	)
	assert denied.status_code == 403

	# an operator may still move it; nothing is orphaned by the move.
	allowed = await client.post(
		f"/v1/threads/{dm_id}/switch",
		headers=admin_headers,
		json={"message_id": first_id},
	)
	assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_participant_state_filters_are_explicit_and_guarded(
	client: AsyncClient,
	admin_auth: dict[str, object],
) -> None:
	"""per-user state filters name their subject; the listing itself is pure."""
	admin_headers = _headers(admin_auth)
	a = await _make_user(client, admin_headers)
	b = await _make_user(client, admin_headers)
	a_id = a["user"]["id"]

	archived_thread = await _create_thread(client, a, title="to archive")
	plain_thread = await _create_thread(client, a, title="stays")

	# a archives one of their threads for themselves (their own state row).
	patched = await client.patch(
		f"/v1/threads/{archived_thread['id']}/participants/users/{a_id}",
		headers=a["headers"],
		json={"archived": True},
	)
	assert patched.status_code == 200
	assert patched.json()["archived"] is True

	# no params: pure access-gated listing, archived state is invisible.
	listed = await client.get("/v1/threads", headers=a["headers"])
	ids = {t["id"] for t in listed.json()}
	assert {plain_thread["id"], archived_thread["id"]} <= ids
	count = await client.get("/v1/threads/count", headers=a["headers"])
	assert count.json() == 2

	# the archived view: only threads a archived.
	archived_view = await client.get(
		f"/v1/threads?archived_by={a_id}", headers=a["headers"]
	)
	archived_ids = {t["id"] for t in archived_view.json()}
	assert archived_thread["id"] in archived_ids
	assert plain_thread["id"] not in archived_ids
	archived_count = await client.get(
		f"/v1/threads/count?archived_by={a_id}", headers=a["headers"]
	)
	assert archived_count.json() == 1

	# the inbox view: the negation, same dimension.
	inbox = await client.get(
		f"/v1/threads?not_archived_by={a_id}", headers=a["headers"]
	)
	inbox_ids = {t["id"] for t in inbox.json()}
	assert plain_thread["id"] in inbox_ids
	assert archived_thread["id"] not in inbox_ids
	inbox_count = await client.get(
		f"/v1/threads/count?not_archived_by={a_id}", headers=a["headers"]
	)
	assert inbox_count.json() == 1

	# reading another user's state requires users:read - plain users refused.
	forbidden = await client.get(
		f"/v1/threads?not_archived_by={a_id}", headers=b["headers"]
	)
	assert forbidden.status_code == 403

	# admins may name another user as the subject, with their own principal.
	admin_view = await client.get(
		f"/v1/threads?not_archived_by={a_id}", headers=admin_headers
	)
	assert admin_view.status_code == 200
	assert archived_thread["id"] not in {t["id"] for t in admin_view.json()}
