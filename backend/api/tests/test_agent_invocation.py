"""B5: mentioning addresses, invoking acts, and the setting that bridges them."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.local_tasks import drain_background_tasks
from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.group import Group, GroupMembership
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.agent import AgentConfig, AgentFeatures, InvokeOnMentionFeature
from api.schemas.message import MessageMention, MessageSplice, TextContent
from api.tests.factories import make_principal
from api.v1.service import access_rules
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.runs import create_message_and_dispatch_invocations
from api.v1.service.runs import launch as runs_service
from api.v1.service.runs.status import run_registry
from api.v1.service.threads.addressing import (
	build_mention_links,
	resolve_invoked_agents,
)
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _settle() -> None:
	"""wait for the invocation background tasks to finish.

	they do real i/o, so yielding the loop a fixed number of times only proves
	how many awaits they happen to contain today.
	"""
	await drain_background_tasks(name_prefix="invoke-agent:", timeout=10.0)


def _use_test_session(
	monkeypatch: pytest.MonkeyPatch,
	session: AsyncSession,
) -> None:
	"""make the orchestrator's own sessions the test's session.

	invocation runs as a background task, so it opens its own scope rather than
	borrowing the request's; in tests that scope points at a connection the
	fixture never created.
	"""

	@asynccontextmanager
	async def _scope() -> AsyncGenerator[AsyncSession]:
		yield session

	monkeypatch.setattr("api.v1.service.runs.invocation.async_session_local", _scope)
	# the durable failure record and the run broadcasts open their own too.
	monkeypatch.setattr("api.v1.service.runs.access.async_session_local", _scope)
	monkeypatch.setattr("api.v1.service.runs.status.async_session_local", _scope)
	monkeypatch.setattr("api.v1.service.events.async_session_local", _scope)


def _stub_run_producer(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
	"""stand in for the agent loop, BELOW the authorization gate.

	deliberately not a stub of ``launch_*``: that is where invocation is
	authorized, so stubbing it would test the call shape and nothing else.
	"""
	started: list[dict[str, object]] = []

	async def _fake_start_run(**kwargs: object) -> TypeID:
		started.append(kwargs)
		return TypeID("run_stub")

	monkeypatch.setattr(runs_service, "_start_run", _fake_start_run)
	return started


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


async def _make_thread(session: AsyncSession, owner: User) -> Thread:
	thread = Thread(owner_id=owner.id, title="invocation")
	session.add(thread)
	await session.commit()
	await session.refresh(thread)
	return thread


async def _make_agent(
	session: AsyncSession,
	name: str,
	reader: User,
	invoke_on_mention: bool = False,
) -> Agent:
	agent = Agent(
		name=name,
		config=AgentConfig(
			features=AgentFeatures(
				invoke_on_mention=InvokeOnMentionFeature(enabled=invoke_on_mention)
			)
		).model_dump(mode="json"),
	)
	session.add(agent)
	await session.commit()
	await session.refresh(agent)
	await access_rules.grant_user_access_unchecked(
		ResourceType.AGENT,
		TypeID(str(agent.id)),
		reader.id,
		session,
		level=AccessLevel.READER,
	)
	return agent


def _mention(agent: Agent) -> MessageMention:
	return MessageMention(type=MentionableSubjectType.AGENT, id=TypeID(str(agent.id)))


@pytest.mark.asyncio
async def test_mention_alone_does_not_invoke(db_session: AsyncSession) -> None:
	"""addressing an agent is not asking it to act."""
	owner = await _make_user(db_session, "inv_quiet_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "quiet-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	mentions = [_mention(agent)]
	_links, participants = await build_mention_links(
		db_session, thread.id, mentions, principal
	)
	invoked = await resolve_invoked_agents(db_session, mentions, participants)
	assert invoked == []


@pytest.mark.asyncio
async def test_invoke_on_mention_bridges_the_two(db_session: AsyncSession) -> None:
	"""the setting is what lets a client that cannot invoke still get an answer."""
	owner = await _make_user(db_session, "inv_bridge_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "bridge-agent", owner, invoke_on_mention=True)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	mentions = [_mention(agent)]
	_links, participants = await build_mention_links(
		db_session, thread.id, mentions, principal
	)
	invoked = await resolve_invoked_agents(db_session, mentions, participants)
	assert [str(a) for a in invoked] == [str(agent.id)]

	# addressing the same agent twice still runs it once.
	duplicate_mentions = [_mention(agent), _mention(agent)]
	_links, participants = await build_mention_links(
		db_session, thread.id, duplicate_mentions, principal
	)
	invoked_once = await resolve_invoked_agents(
		db_session, duplicate_mentions, participants
	)
	assert [str(a) for a in invoked_once] == [str(agent.id)]


@pytest.mark.asyncio
async def test_message_rejects_multiple_invoked_agents_before_persisting(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "inv_multi_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agents = [
		await _make_agent(
			db_session,
			f"multi-agent-{index}",
			owner,
			invoke_on_mention=True,
		)
		for index in range(2)
	]
	for agent in agents:
		await thread_service.add_agents(
			db_session,
			principal,
			thread.id,
			[agent.id],
		)
	with pytest.raises(HTTPException) as unsupported:
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="@a @b")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				mentions=[_mention(agent) for agent in agents],
			),
			db_session,
			principal,
		)
	assert unsupported.value.status_code == 501
	assert (
		await db_session.scalar(
			select(Message.id).where(Message.thread_id == thread.id)
		)
		is None
	)


@pytest.mark.asyncio
async def test_thread_override_beats_the_agent_default(
	db_session: AsyncSession,
) -> None:
	"""a chat can opt an agent in or out without touching the agent itself."""
	owner = await _make_user(db_session, "inv_override_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	eager = await _make_agent(db_session, "eager-agent", owner, invoke_on_mention=True)
	quiet = await _make_agent(db_session, "reserved-agent", owner)
	for agent in (eager, quiet):
		await thread_service.add_agents(
			db_session, principal, thread.id, [TypeID(str(agent.id))]
		)

	await thread_service.update_agent_participant(
		db_session, principal, thread.id, TypeID(str(eager.id)), False
	)
	await thread_service.update_agent_participant(
		db_session, principal, thread.id, TypeID(str(quiet.id)), True
	)
	mentions = [_mention(eager), _mention(quiet)]
	_links, participants = await build_mention_links(
		db_session, thread.id, mentions, principal
	)
	invoked = await resolve_invoked_agents(db_session, mentions, participants)
	assert invoked == [quiet.id]

	# dropping the override falls back to the agent's own setting.
	await thread_service.update_agent_participant(
		db_session, principal, thread.id, TypeID(str(eager.id)), None
	)
	_links, participants = await build_mention_links(
		db_session, thread.id, [_mention(eager)], principal
	)
	assert await resolve_invoked_agents(
		db_session, [_mention(eager)], participants
	) == [eager.id]


@pytest.mark.asyncio
async def test_invoking_a_non_participant_agent_is_rejected(
	db_session: AsyncSession,
) -> None:
	"""an agent that is not in the thread cannot be addressed, so it never runs."""
	owner = await _make_user(db_session, "inv_absent_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(
		db_session, "absent-invoked-agent", owner, invoke_on_mention=True
	)

	with pytest.raises(HTTPException) as rejected:
		await build_mention_links(
			db_session,
			TypeID(str(thread.id)),
			[_mention(agent)],
			principal,
		)
	assert rejected.value.status_code == 422


@pytest.mark.asyncio
async def test_user_mentions_are_stored_without_invoking_anything(
	db_session: AsyncSession,
) -> None:
	"""user mentions are addressing only - accepted, persisted, inert for now."""
	owner = await _make_user(db_session, "inv_user_owner")
	mate = await _make_user(db_session, "inv_user_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD, thread.id, mate.id, db_session, level=AccessLevel.EDITOR
	)

	message = (
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="@mate look at this")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				mentions=[
					MessageMention(type=MentionableSubjectType.USER, id=TypeID(mate.id))
				],
			),
			db_session,
			principal=principal,
		)
	).message
	assert message.mentions == [{"type": MentionableSubjectType.USER, "id": mate.id}]
	assert message.mentioned_agent_ids == []


@pytest.mark.asyncio
async def test_user_mentions_follow_group_thread_access(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "inv_group_owner")
	mate = await _make_user(db_session, "inv_group_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	group = Group(name="invocation group", owner_id=owner.id)
	db_session.add(group)
	await db_session.flush()
	db_session.add(GroupMembership(group_id=group.id, user_id=mate.id))
	await db_session.flush()
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD, thread.id, group.id, db_session
	)

	written = await thread_service.create_message(
		thread.id,
		MessageDraft(
			content=[TextContent(text="@mate look")],
			type=MessageType.USER,
			sender_user_id=owner.id,
			mentions=[MessageMention(type=MentionableSubjectType.USER, id=mate.id)],
		),
		db_session,
		principal=principal,
	)
	assert written.message.mentions == [
		{"type": MentionableSubjectType.USER, "id": mate.id}
	]


@pytest.mark.asyncio
async def test_stale_participant_state_does_not_make_user_addressable(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "inv_stale_owner")
	stranger = await _make_user(db_session, "inv_stale_stranger")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	db_session.add(ThreadParticipant(thread_id=thread.id, user_id=stranger.id))
	await db_session.flush()

	with pytest.raises(HTTPException) as rejected:
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="@stranger")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				mentions=[
					MessageMention(
						type=MentionableSubjectType.USER,
						id=stranger.id,
					)
				],
			),
			db_session,
			principal=principal,
		)
	assert rejected.value.status_code == 404


@pytest.mark.asyncio
async def test_mentioning_an_unreachable_user_is_rejected(
	db_session: AsyncSession,
) -> None:
	"""addressing resolves through the one visibility rule: a stranger who
	shares no thread and no friendship cannot be named."""
	owner = await _make_user(db_session, "inv_reach_owner")
	stranger = await _make_user(db_session, "inv_reach_stranger")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)

	with pytest.raises(HTTPException) as rejected:
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="@stranger")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				mentions=[
					MessageMention(
						type=MentionableSubjectType.USER, id=TypeID(stranger.id)
					)
				],
			),
			db_session,
			principal=principal,
		)
	assert rejected.value.status_code == 404


@pytest.mark.asyncio
async def test_posting_an_invocation_starts_a_run(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""the headline behavior: mentioning an agent that answers on mention makes
	the server run it, with no second call from the client.

	stubbed BELOW the authorization gate, so this goes through the real one -
	the gate is the thing that was broken.
	"""
	owner = await _make_user(db_session, "inv_e2e_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "e2e-agent", owner, invoke_on_mention=True)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	_use_test_session(monkeypatch, db_session)
	started = _stub_run_producer(monkeypatch)

	message = await create_message_and_dispatch_invocations(
		thread.id,
		MessageDraft(
			content=[TextContent(text="do the thing")],
			type=MessageType.USER,
			sender_user_id=owner.id,
			mentions=[_mention(agent)],
		),
		db_session,
		principal=principal,
	)
	await _settle()

	assert len(started) == 1
	assert str(started[0]["agent_id"]) == str(agent.id)
	# the run answers the message that invoked it, and does not re-send it.
	assert str(started[0]["invoking_message_id"]) == str(message.id)
	assert started[0]["input"] is None


@pytest.mark.asyncio
async def test_committed_invocation_dispatches_after_delivery_failure(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import invocation as invocation_service
	from api.v1.service.threads.messages.writes import (
		CommittedMessageWriteError,
		WrittenMessage,
	)

	principal = make_principal(slug="committed-invocation")
	thread_id = TypeID(new_typeid("thread"))
	message_id = TypeID(new_typeid("msg"))
	agent_id = TypeID(new_typeid("agent"))
	written = WrittenMessage(
		message=SimpleNamespace(id=message_id),
		splice=MessageSplice(parent_id=None),
		invoked_agent_ids=[agent_id],
	)
	monkeypatch.setattr(
		invocation_service,
		"create_message_with_commit_outcome",
		AsyncMock(
			side_effect=CommittedMessageWriteError(
				written,
				RuntimeError("fanout failed"),
			)
		),
	)
	answer = AsyncMock()
	monkeypatch.setattr(invocation_service, "_answer_invocation", answer)

	with pytest.raises(RuntimeError, match="fanout failed"):
		await invocation_service.create_message_and_dispatch_invocations(
			thread_id,
			MessageDraft(content=[TextContent(text="invoke")]),
			db_session,
			principal,
		)
	await asyncio.sleep(0)

	answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_plain_message_starts_nothing(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""ordinary conversation must never wake an agent."""
	owner = await _make_user(db_session, "inv_plain_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "plain-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	_use_test_session(monkeypatch, db_session)
	started = _stub_run_producer(monkeypatch)

	await create_message_and_dispatch_invocations(
		thread.id,
		MessageDraft(
			content=[TextContent(text="just talking, and mentioning nobody")],
			type=MessageType.USER,
			sender_user_id=owner.id,
		),
		db_session,
		principal=principal,
	)
	await _settle()

	assert started == []


@pytest.mark.asyncio
async def test_two_invocations_of_one_agent_start_a_single_run(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""one agent answering one conversation is one run: the second invocation
	catches that run up instead of starting a rival."""
	owner = await _make_user(db_session, "inv_race_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "race-agent", owner, invoke_on_mention=True)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	starts = 0
	release = asyncio.Event()

	async def _slow_start_run(**kwargs: object) -> TypeID:
		nonlocal starts
		starts += 1
		# hold the slot open the way a real start does while it registers.
		await release.wait()
		run_id = TypeID("run_race")
		await run_registry.start_run(
			run_id,
			TypeID(agent.id),
			owner.id,
			thread.id,
		)
		await run_registry.bind(
			run_id,
			container_root_id=None,
			invocation_message_id=None,
		)
		return run_id

	steered: list[TypeID] = []

	async def _fake_steer(thread_id, run_id, message_id, principal):  # noqa: ANN001
		steered.append(message_id)
		return True

	_use_test_session(monkeypatch, db_session)
	monkeypatch.setattr(runs_service, "_start_run", _slow_start_run)
	monkeypatch.setattr("api.v1.service.runs.invocation._steer", _fake_steer)

	draft = MessageDraft(
		content=[TextContent(text="@agent first")],
		type=MessageType.USER,
		sender_user_id=owner.id,
		mentions=[_mention(agent)],
	)
	await create_message_and_dispatch_invocations(
		thread.id, draft, db_session, principal=principal
	)
	await _settle()

	second = MessageDraft(
		content=[TextContent(text="@agent again")],
		type=MessageType.USER,
		sender_user_id=owner.id,
		mentions=[_mention(agent)],
	)
	await create_message_and_dispatch_invocations(
		thread.id, second, db_session, principal=principal
	)
	await _settle()

	release.set()
	await _settle()

	# the first invocation owns the slot; the second waits on it rather than
	# concluding "nobody is answering" and starting its own.
	assert starts == 1
	await run_registry.complete_run(TypeID("run_race"))
