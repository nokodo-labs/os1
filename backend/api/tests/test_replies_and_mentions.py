"""B5: semantic replies, structured mentions, and run-block ordering.

the invariant under test throughout: what a message ANSWERS is independent of
where it SITS, and a run's output belongs to the snapshot the run actually read.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.message import Message, MessageType, UserMessage
from api.models.thread import Thread
from api.models.user import User
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.message import (
	MessageCreate,
	MessageMention,
	MessageRange,
	MessageSplice,
	RunBlockRef,
	TextContent,
)
from api.schemas.runs import RunRequest
from api.v1.service import access_rules
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.runs.contracts import PersistedRunInput
from api.v1.service.threads.drafts import MessageDraft
from api.v1.service.threads.splices import PreparedPlacement, replacement_messages
from nokodo_ai.types.sentinels import MissingType
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _make_user(session: AsyncSession, slug: str) -> User:
	user = User(
		email=f"{slug}@example.com",
		username=slug,
		hashed_password="password",
		is_active=True,
		is_superuser=False,
	)
	session.add(user)
	await session.commit()
	await session.refresh(user)
	return user


async def _make_thread(session: AsyncSession, owner: User, title: str) -> Thread:
	thread = Thread(owner_id=owner.id, title=title)
	session.add(thread)
	await session.commit()
	await session.refresh(thread)
	return thread


async def _make_agent(session: AsyncSession, name: str, reader: User) -> Agent:
	agent = Agent(name=name)
	session.add(agent)
	await session.commit()
	await session.refresh(agent)
	# mentioning an agent requires reading it, so grant that explicitly.
	await access_rules.grant_user_access_unchecked(
		ResourceType.AGENT,
		TypeID(str(agent.id)),
		reader.id,
		session,
		level=AccessLevel.READER,
	)
	return agent


async def _share(session: AsyncSession, thread_id: TypeID, user: User) -> None:
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		user.id,
		session,
		level=AccessLevel.EDITOR,
	)


async def _post(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	text: str,
	parent_id: TypeID | None = None,
	reply_to_message_id: TypeID | None = None,
	mentions: list[MessageMention] | None = None,
) -> Message:
	draft = MessageDraft(
		content=[TextContent(text=text)],
		type=MessageType.USER,
		sender_user_id=principal.user.id,
		reply_to_message_id=reply_to_message_id,
		mentions=mentions or [],
	)
	if parent_id is not None:
		draft.splice = MessageSplice(parent_id=parent_id)
	written = await thread_service.create_message(
		thread_id, draft, session, principal=principal
	)
	return written.message


async def _chain(session: AsyncSession, thread_id: TypeID) -> list[str]:
	"""the thread's messages, ordered by parent links from the root."""
	rows = list(
		(
			await session.execute(
				Message.__table__.select().where(Message.thread_id == str(thread_id))
			)
		).all()
	)
	by_parent: dict[str | None, str] = {
		(str(row.parent_id) if row.parent_id else None): str(row.id) for row in rows
	}
	order: list[str] = []
	cursor: str | None = None
	while (nxt := by_parent.get(cursor)) is not None:
		order.append(nxt)
		cursor = nxt
	return order


async def _generated(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	run_id: TypeID,
	text: str,
	parent_id: TypeID | None,
	message_type: MessageType = MessageType.ASSISTANT,
) -> Message:
	draft = MessageDraft(
		content=[TextContent(text=text)],
		type=message_type,
		metadata={"run_id": str(run_id)},
		splice=MessageSplice(parent_id=parent_id),
	)
	written = await thread_service.create_message(
		thread_id,
		draft,
		session,
		principal=principal,
	)
	return written.message


def test_run_request_preserves_explicit_null_splice_parent() -> None:
	req = RunRequest.model_validate(
		{
			"thread_id": new_typeid("thread"),
			"agent_id": new_typeid("agent"),
			"input": {"content": "edited root"},
			"splice": {"parent_id": None},
		}
	)
	assert req.splice is not None
	assert req.splice.parent_id is None


@pytest.mark.asyncio
async def test_replace_run_block_atomically_splices_canon(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "replace_canon_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "replace canon")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	old_run_id = TypeID(new_typeid("run"))
	o1 = await _generated(
		db_session, thread.id, principal, old_run_id, "old answer", anchor.id
	)
	o2 = await _generated(
		db_session,
		thread.id,
		principal,
		old_run_id,
		"old tool",
		o1.id,
		MessageType.TOOL,
	)
	successor = await _post(db_session, thread.id, principal, "later message")
	new_id = TypeID(new_typeid("msg"))
	written = await thread_service.create_message(
		thread.id,
		MessageDraft(
			type=MessageType.ASSISTANT,
			content=[TextContent(text="new answer")],
			metadata={"run_id": str(new_typeid("run"))},
			splice=MessageSplice(
				parent_id=anchor.id,
				reparent_message_ids=[successor.id],
				replaces=MessageRange(head_id=o1.id, tail_id=o2.id),
			),
		),
		db_session,
		principal,
		message_id=new_id,
	)
	replacement = written.message
	assert replacement.id == new_id
	assert replacement.parent_id == anchor.id
	await db_session.refresh(successor)
	assert successor.parent_id == new_id
	assert await db_session.get(Message, o1.id) is None
	assert await db_session.get(Message, o2.id) is None
	await db_session.refresh(thread)
	assert thread.current_message_id == successor.id
	new_run_id = TypeID(str(replacement.public_metadata["run_id"]))
	n2 = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			type=MessageType.TOOL,
			content=[TextContent(text="new tool")],
			metadata={"run_id": str(new_run_id)},
		),
		replacement.id,
		new_run_id,
		db_session,
		principal,
		message_id=TypeID(new_typeid("msg")),
		read_through_message_id=anchor.id,
	)
	await db_session.refresh(successor)
	assert n2.message.parent_id == replacement.id
	assert successor.parent_id == n2.message.id


@pytest.mark.asyncio
async def test_replace_run_block_rejects_external_reply(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "replace_reply_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "replace reply")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	run_id = TypeID(new_typeid("run"))
	old = await _generated(
		db_session, thread.id, principal, run_id, "old answer", anchor.id
	)
	await _post(
		db_session,
		thread.id,
		principal,
		"reply elsewhere",
		reply_to_message_id=old.id,
	)
	with pytest.raises(HTTPException) as conflict:
		await replacement_messages(
			db_session,
			thread.id,
			RunBlockRef(run_id=run_id, run_head_message_id=old.id),
		)
	assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_message_range_rejects_external_reply_and_child(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "range_isolation_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "range isolation")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	head = await _generated(
		db_session,
		thread.id,
		principal,
		TypeID(new_typeid("run")),
		"replace me",
		anchor.id,
	)
	tail = await _generated(
		db_session,
		thread.id,
		principal,
		TypeID(new_typeid("run")),
		"and me",
		head.id,
	)
	side_child = await _post(
		db_session, thread.id, principal, "side child", parent_id=head.id
	)
	with pytest.raises(HTTPException) as child_conflict:
		await replacement_messages(
			db_session,
			thread.id,
			MessageRange(head_id=head.id, tail_id=tail.id),
		)
	assert child_conflict.value.status_code == 409

	await db_session.execute(delete(Message).where(Message.id == side_child.id))
	await _post(
		db_session,
		thread.id,
		principal,
		"external reply",
		reply_to_message_id=head.id,
	)
	with pytest.raises(HTTPException) as reply_conflict:
		await replacement_messages(
			db_session,
			thread.id,
			MessageRange(head_id=head.id, tail_id=tail.id),
		)
	assert reply_conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_launch_thread_run_preflights_replacement_without_passing_plan(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "replace_launch_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "replace launch")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	run_id = TypeID(new_typeid("run"))
	old = await _generated(
		db_session, thread.id, principal, run_id, "old answer", anchor.id
	)
	captured: dict[str, object] = {}
	expected_run_id = TypeID(new_typeid("run"))

	async def _capture_start(**kwargs: object) -> TypeID:
		captured.update(kwargs)
		return expected_run_id

	monkeypatch.setattr(runs_service, "_start_run", _capture_start)
	launched = await runs_service.launch_thread_run(
		db_session,
		thread.id,
		TypeID(new_typeid("agent")),
		principal,
		splice=MessageSplice(
			parent_id=anchor.id,
			replaces=RunBlockRef(
				run_id=run_id,
				run_head_message_id=old.id,
			),
		),
	)
	assert launched == expected_run_id
	assert captured["splice"] is not None
	assert isinstance(captured["run_id"], str)


@pytest.mark.asyncio
async def test_launch_thread_run_persists_input_before_starting_run(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "anchor_first_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "anchor first")
	captured: dict[str, object] = {}

	async def _capture_start(**kwargs: object) -> TypeID:
		captured.update(kwargs)
		persisted_input = kwargs["persisted_input"]
		assert isinstance(persisted_input, PersistedRunInput)
		assert await db_session.get(Message, persisted_input.message_id) is not None
		run_id = kwargs["run_id"]
		assert isinstance(run_id, TypeID)
		return run_id

	monkeypatch.setattr(runs_service, "_start_run", _capture_start)
	run_id = await runs_service.launch_thread_run(
		db_session,
		thread.id,
		TypeID(new_typeid("agent")),
		principal,
		input=MessageCreate(content="hello"),
	)
	persisted_input = captured["persisted_input"]
	assert isinstance(persisted_input, PersistedRunInput)
	persisted = await db_session.get(Message, persisted_input.message_id)
	assert persisted is not None
	assert persisted.public_metadata["run_id"] == str(run_id)
	assert captured["input"] is None
	assert captured["splice"] is None
	assert isinstance(persisted_input.splice, MessageSplice)
	# captured at the write, not re-read: the producer never queries it again.
	assert persisted_input.sdk_message.text == "hello"


@pytest.mark.asyncio
async def test_launch_thread_run_places_input_on_the_head_that_won_the_lock(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the head is re-read under the lock, not carried in from the preflight.

	a writer that commits while the launch queues for the thread lock advances
	the head; placing against the pre-lock one chains the run's input onto a
	stale parent and takes the other message off canon - silent loss in a
	multi-writer thread, where an off-canon message with no branch pointer
	stops being selected at all.
	"""
	from api.v1.service.runs import launch as runs_service
	from api.v1.service.threads import splices as splices_module

	owner = await _make_user(db_session, "stale_head_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "stale head")
	first = await _post(db_session, thread.id, principal, "first")

	competing: dict[str, Message] = {}
	real_prepare = splices_module.prepare_message_placement

	async def _advance_head_then_prepare(
		session: AsyncSession,
		target: Thread,
		requested: MessageSplice | MissingType,
		message_id: TypeID,
		principal: Principal,
		advances_head: bool = True,
	) -> PreparedPlacement:
		"""stand in for a writer that commits while the launch holds the lock."""
		if "competing" not in competing:
			competing["competing"] = await _post(
				db_session, thread.id, principal, "competing"
			)
		return await real_prepare(
			session,
			target,
			requested,
			message_id,
			principal=principal,
			advances_head=advances_head,
		)

	monkeypatch.setattr(
		runs_service, "prepare_message_placement", _advance_head_then_prepare
	)

	captured: dict[str, object] = {}

	async def _capture_start(**kwargs: object) -> TypeID:
		captured.update(kwargs)
		run_id = kwargs["run_id"]
		assert isinstance(run_id, TypeID)
		return run_id

	monkeypatch.setattr(runs_service, "_start_run", _capture_start)

	await runs_service.launch_thread_run(
		db_session,
		thread.id,
		TypeID(new_typeid("agent")),
		principal,
		input=MessageCreate(content="mine"),
	)

	persisted_input = captured["persisted_input"]
	assert isinstance(persisted_input, PersistedRunInput)
	written = await db_session.get(Message, persisted_input.message_id)
	assert written is not None
	assert written.parent_id == competing["competing"].id
	assert written.parent_id != first.id


@pytest.mark.asyncio
async def test_launch_thread_run_rejects_empty_thread_without_anchor(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "anchor_required_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "anchor required")
	started = False

	async def _unexpected_start(**_kwargs: object) -> TypeID:
		nonlocal started
		started = True
		return TypeID(new_typeid("run"))

	monkeypatch.setattr(runs_service, "_start_run", _unexpected_start)
	with pytest.raises(HTTPException) as invalid:
		await runs_service.launch_thread_run(
			db_session,
			thread.id,
			TypeID(new_typeid("agent")),
			principal,
		)
	assert invalid.value.status_code == 422
	assert not started


@pytest.mark.asyncio
async def test_launch_thread_run_rejects_unknown_parent_before_start(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "unknown_parent_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "unknown parent")
	await _post(db_session, thread.id, principal, "anchor")
	started = False

	async def _unexpected_start(**_kwargs: object) -> TypeID:
		nonlocal started
		started = True
		return TypeID(new_typeid("run"))

	monkeypatch.setattr(runs_service, "_start_run", _unexpected_start)
	with pytest.raises(HTTPException) as not_found:
		await runs_service.launch_thread_run(
			db_session,
			thread.id,
			TypeID(new_typeid("agent")),
			principal,
			splice=MessageSplice(parent_id=TypeID(new_typeid("msg"))),
		)
	assert not_found.value.status_code == 404
	assert not started


@pytest.mark.asyncio
async def test_launch_thread_run_preflights_before_claiming_slot(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "preflight_before_slot_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "preflight before slot")
	await _post(db_session, thread.id, principal, "anchor")
	claim = AsyncMock()
	monkeypatch.setattr(runs_service.agent_slots, "claim", claim)

	with pytest.raises(HTTPException) as not_found:
		await runs_service.launch_thread_run(
			db_session,
			thread.id,
			TypeID(new_typeid("agent")),
			principal,
			splice=MessageSplice(parent_id=TypeID(new_typeid("msg"))),
		)

	assert not_found.value.status_code == 404
	claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_thread_run_refuses_same_agent_conversation(
	db_session: AsyncSession,
) -> None:
	from api.v1.service.runs import launch as runs_service
	from api.v1.service.runs.status import run_conversations, run_registry

	owner = await _make_user(db_session, "duplicate_run_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "duplicate run")
	agent_id = TypeID(new_typeid("agent"))
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(run_id, agent_id, owner.id, thread.id)
	await run_conversations.bind(run_id, None, None)
	try:
		with pytest.raises(HTTPException) as conflict:
			await runs_service.launch_thread_run(
				db_session,
				thread.id,
				agent_id,
				principal,
				input=MessageCreate(content="valid input"),
			)
		assert conflict.value.status_code == 409
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_launch_thread_run_rejects_hidden_invoking_message(
	db_session: AsyncSession,
) -> None:
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "hidden_invocation_owner")
	mate = await _make_user(db_session, "hidden_invocation_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "hidden invocation")
	agent = await _make_agent(db_session, "hidden-invocation-agent", owner)
	await thread_service.add_agents(
		db_session,
		principal,
		thread.id,
		[agent.id],
	)
	root = await _post(db_session, thread.id, principal, "root")
	await _post(db_session, thread.id, principal, "canon tail")
	await _share(db_session, thread.id, mate)
	hidden = await _post(
		db_session,
		thread.id,
		principal,
		"@agent",
		parent_id=root.id,
		mentions=[
			MessageMention(
				type=MentionableSubjectType.AGENT,
				id=agent.id,
			)
		],
	)
	hidden.branch_current_message_id = None
	await db_session.commit()

	with pytest.raises(HTTPException) as not_found:
		await runs_service.launch_thread_run(
			db_session,
			thread.id,
			agent.id,
			principal,
			invoking_message_id=hidden.id,
		)
	assert not_found.value.status_code == 404


@pytest.mark.asyncio
async def test_reply_to_older_message_stays_inline(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	"""the whole point of a semantic anchor: answering an older message must
	not fork the conversation the way an explicit parent would."""
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread_resp = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "replies"},
		headers=headers,
	)
	assert thread_resp.status_code == 201
	thread_id = thread_resp.json()["id"]

	first = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "the original question"},
		headers=headers,
	)
	assert first.status_code == 201
	first_id = first.json()["id"]

	second = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "unrelated chatter"},
		headers=headers,
	)
	assert second.status_code == 201
	second_id = second.json()["id"]

	reply = await client.post(
		f"/v1/threads/{thread_id}/messages",
		json={"content": "answering the first one", "reply_to_message_id": first_id},
		headers=headers,
	)
	assert reply.status_code == 201
	body = reply.json()
	assert body["reply_to_message_id"] == first_id
	# inline: it continues the conversation, it does not hang off its anchor.
	assert body["parent_id"] == second_id
	assert body["branch_current_message_id"] is None

	page = await client.get(f"/v1/threads/{thread_id}/branch", headers=headers)
	assert page.status_code == 200
	page_body = page.json()
	assert [m["id"] for m in page_body["messages"]] == [
		first_id,
		second_id,
		body["id"],
	]
	assert page_body["siblings"] == []


@pytest.mark.asyncio
async def test_reply_target_outside_the_thread_is_rejected(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	first_thread = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "one"},
		headers=headers,
	)
	other_thread = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "two"},
		headers=headers,
	)
	foreign = await client.post(
		f"/v1/threads/{other_thread.json()['id']}/messages",
		json={"content": "elsewhere"},
		headers=headers,
	)

	rejected = await client.post(
		f"/v1/threads/{first_thread.json()['id']}/messages",
		json={"content": "reply", "reply_to_message_id": foreign.json()["id"]},
		headers=headers,
	)
	assert rejected.status_code == 404

	missing = await client.post(
		f"/v1/threads/{first_thread.json()['id']}/messages",
		json={"content": "reply", "reply_to_message_id": new_typeid("msg")},
		headers=headers,
	)
	assert missing.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_reply_target_keeps_the_reply(
	db_session: AsyncSession,
) -> None:
	"""the anchor is a reference, not a dependency: deleting a message the
	reply does not descend from must not take the reply with it."""
	owner = await _make_user(db_session, "replydel_owner")
	mate = await _make_user(db_session, "replydel_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "reply deletion")
	first = await _post(db_session, thread.id, principal, "first")
	await _post(db_session, thread.id, principal, "canon tail")
	await _share(db_session, thread.id, mate)

	# a sub-thread hanging off an earlier message: visible, but not an
	# ancestor of anything on canon.
	aside = await _post(
		db_session,
		thread.id,
		principal,
		"aside",
		parent_id=TypeID(str(first.id)),
	)
	reply = await _post(
		db_session,
		thread.id,
		principal,
		"answering the aside from canon",
		reply_to_message_id=TypeID(str(aside.id)),
	)
	assert str(reply.reply_to_message_id) == str(aside.id)

	await thread_service.delete_user_message_turn(
		thread.id, TypeID(str(aside.id)), db_session, principal=principal
	)

	surviving = await db_session.get(Message, str(reply.id))
	assert surviving is not None
	await db_session.refresh(surviving)
	assert surviving.reply_to_message_id is None


@pytest.mark.asyncio
async def test_mentions_are_structured_and_survive_edits(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "mention_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "mentions")
	agent = await _make_agent(db_session, "mention-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	message = await _post(
		db_session,
		thread.id,
		principal,
		"@agent look at this",
		mentions=[
			MessageMention(type=MentionableSubjectType.AGENT, id=TypeID(str(agent.id)))
		],
	)
	assert message.mentioned_agent_ids == [agent.id]

	from api.schemas.message import MessageUpdate

	edited = await thread_service.update_user_message(
		thread.id,
		TypeID(str(message.id)),
		MessageUpdate(content="@agent look at this instead"),
		db_session,
		principal=principal,
	)
	# the relation is not parsed from content, so editing cannot lose it.
	assert edited.mentioned_agent_ids == [agent.id]
	assert await thread_service.message_mentions_agent(
		db_session,
		thread.id,
		TypeID(str(message.id)),
		TypeID(str(agent.id)),
	)


@pytest.mark.asyncio
async def test_mentioning_a_non_participant_agent_is_rejected(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "mentionpart_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "non participant")
	agent = await _make_agent(db_session, "absent-agent", owner)

	with pytest.raises(HTTPException) as rejected:
		await _post(
			db_session,
			thread.id,
			principal,
			"@agent",
			mentions=[
				MessageMention(
					type=MentionableSubjectType.AGENT, id=TypeID(str(agent.id))
				)
			],
		)
	assert rejected.value.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_mentions_are_rejected_on_the_wire(
	client: AsyncClient,
	user_auth: dict[str, object],
) -> None:
	headers = user_auth["headers"]
	assert isinstance(headers, dict)
	user = user_auth["user"]
	assert isinstance(user, dict)

	thread = await client.post(
		"/v1/threads",
		json={"owner_id": user["id"], "title": "dupes"},
		headers=headers,
	)
	agent_id = new_typeid("agent")
	rejected = await client.post(
		f"/v1/threads/{thread.json()['id']}/messages",
		json={
			"content": "hi",
			"mentions": [
				{"type": "agent", "id": agent_id},
				{"type": "agent", "id": agent_id},
			],
		},
		headers=headers,
	)
	assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_run_output_is_spliced_before_conversation_it_never_saw(
	db_session: AsyncSession,
) -> None:
	"""a run answers the snapshot it read. messages posted since then are not
	part of that answer, so they must end up AFTER it."""
	owner = await _make_user(db_session, "block_owner")
	mate = await _make_user(db_session, "block_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	mate_principal = Principal.for_user(
		user=mate, group_ids=(), permissions=frozenset()
	)
	thread = await _make_thread(db_session, owner, "run tail")
	await _share(db_session, thread.id, mate)
	run_id = TypeID(new_typeid("run"))

	invocation = await _post(db_session, thread.id, principal, "@agent investigate")
	first_answer = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="first answer chunk")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": run_id},
		),
		TypeID(str(invocation.id)),
		run_id,
		db_session,
		principal=principal,
	)

	# conversation continues while the run is still on its old snapshot.
	interjection = await _post(db_session, thread.id, mate_principal, "use staging")
	follow_up = await _post(db_session, thread.id, mate_principal, "postgres 17 only")

	draft = MessageDraft(
		content=[TextContent(text="second answer chunk")],
		type=MessageType.ASSISTANT,
	)
	spliced = await thread_service.create_message_at_run_tail(
		thread.id,
		draft,
		TypeID(str(first_answer.message.id)),
		run_id,
		db_session,
		principal=principal,
	)

	assert await _chain(db_session, thread.id) == [
		str(invocation.id),
		str(first_answer.message.id),
		str(spliced.message.id),
		str(interjection.id),
		str(follow_up.id),
	]
	# only the displaced message moved; its own descendants did not.
	moved = await db_session.get(Message, str(interjection.id))
	assert moved is not None
	assert str(moved.parent_id) == str(spliced.message.id)
	tail = await db_session.get(Message, str(follow_up.id))
	assert tail is not None
	assert str(tail.parent_id) == str(interjection.id)
	# the conversation still ends where the humans left it.
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(follow_up.id)


@pytest.mark.asyncio
async def test_run_output_reparents_every_tail_child(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "multi_child_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "multi child tail")
	run_id = TypeID(new_typeid("run"))
	tail = await _post(db_session, thread.id, principal, "tail")
	children = [
		UserMessage(
			thread_id=thread.id,
			parent_id=tail.id,
			type=MessageType.USER,
			content=[{"type": "text", "text": f"child {index}"}],
			sender_user_id=owner.id,
		)
		for index in range(2)
	]
	db_session.add_all(children)
	await db_session.flush()
	thread.current_message_id = children[-1].id
	await db_session.commit()
	written = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="inserted")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": str(run_id)},
		),
		tail.id,
		run_id,
		db_session,
		principal,
	)
	for child in children:
		await db_session.refresh(child)
		assert child.parent_id == written.message.id
	assert written.splice.reparent_message_ids == [child.id for child in children]


@pytest.mark.asyncio
async def test_splice_inside_a_sub_thread_keeps_the_chain_leaf(
	db_session: AsyncSession,
) -> None:
	"""splicing is an insertion, not an append: the sub-thread still ends where
	it did, or its later messages vanish from paging and the next post there
	roots a nested sub-thread."""
	owner = await _make_user(db_session, "subsplice_owner")
	mate = await _make_user(db_session, "subsplice_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	mate_principal = Principal.for_user(
		user=mate, group_ids=(), permissions=frozenset()
	)
	thread = await _make_thread(db_session, owner, "sub-thread splice")
	await _share(db_session, thread.id, mate)
	run_id = TypeID(new_typeid("run"))

	root = await _post(db_session, thread.id, principal, "canon root")
	head = await _post(db_session, thread.id, mate_principal, "canon head")

	# two writers, so a non-head parent opens a sub-thread rather than branching.
	sub_root = await _post(
		db_session, thread.id, principal, "@agent look here", parent_id=root.id
	)
	# each post targets the chain's own leaf, which extends that chain rather
	# than opening another one.
	sub_answer = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="first answer")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": run_id},
		),
		TypeID(str(sub_root.id)),
		run_id,
		db_session,
		principal=principal,
	)
	interjection = await _post(
		db_session,
		thread.id,
		mate_principal,
		"wait",
		parent_id=sub_answer.message.id,
	)

	spliced = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="second answer")],
			type=MessageType.ASSISTANT,
		),
		TypeID(str(sub_answer.message.id)),
		run_id,
		db_session,
		principal=principal,
	)

	moved = await db_session.get(Message, str(interjection.id))
	assert moved is not None
	assert str(moved.parent_id) == str(spliced.message.id)

	# the chain leaf must still be the real tail, NOT the spliced message.
	chain_root = await db_session.get(Message, str(sub_root.id))
	assert chain_root is not None
	await db_session.refresh(chain_root, attribute_names=["branch_current_message_id"])
	assert str(chain_root.branch_current_message_id) == str(interjection.id)

	# canon is untouched by any of it.
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(head.id)


@pytest.mark.asyncio
async def test_run_output_extends_normally_when_nothing_intervened(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "blocktail_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "quiet run")

	invocation = await _post(db_session, thread.id, principal, "@agent")
	answer = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="answer")],
			type=MessageType.ASSISTANT,
		),
		TypeID(str(invocation.id)),
		TypeID(new_typeid("run")),
		db_session,
		principal=principal,
	)

	assert str(answer.message.parent_id) == str(invocation.id)
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(answer.message.id)


@pytest.mark.asyncio
async def test_regeneration_relocates_prior_output_after_the_new_answer(
	db_session: AsyncSession,
) -> None:
	"""a retry inserts before every existing child of the snapshot it read."""
	owner = await _make_user(db_session, "regen_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "regen")
	first_run_id = TypeID(new_typeid("run"))
	second_run_id = TypeID(new_typeid("run"))

	invocation = await _post(db_session, thread.id, principal, "@agent explain")
	first = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="first answer")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": first_run_id},
		),
		TypeID(str(invocation.id)),
		first_run_id,
		db_session,
		principal=principal,
	)

	# the retry run read the conversation through the invocation - the first
	# answer is its own prior output, not unseen traffic.
	second = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="second answer")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": second_run_id},
		),
		TypeID(str(invocation.id)),
		second_run_id,
		db_session,
		principal=principal,
		read_through_message_id=TypeID(str(invocation.id)),
	)

	# the old answer is relocated under the new answer.
	assert str(second.message.parent_id) == str(invocation.id)
	stored_first = await db_session.get(Message, str(first.message.id))
	assert stored_first is not None
	assert stored_first.parent_id == second.message.id
	# and the conversation now ends at the retry.
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(second.message.id)


@pytest.mark.asyncio
async def test_separate_run_answer_relocates_the_existing_child(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "multi_run_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "multiple runs")
	invocation = await _post(db_session, thread.id, principal, "@agents explain")
	first_run_id = TypeID(new_typeid("run"))
	second_run_id = TypeID(new_typeid("run"))

	first = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="first run answer")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": first_run_id},
		),
		invocation.id,
		first_run_id,
		db_session,
		principal=principal,
	)
	second = await thread_service.create_message_at_run_tail(
		thread.id,
		MessageDraft(
			content=[TextContent(text="second run answer")],
			type=MessageType.ASSISTANT,
			metadata={"run_id": second_run_id},
		),
		invocation.id,
		second_run_id,
		db_session,
		principal=principal,
		read_through_message_id=invocation.id,
	)

	await db_session.refresh(first.message)
	assert first.message.parent_id == second.message.id
	assert second.message.parent_id == invocation.id
