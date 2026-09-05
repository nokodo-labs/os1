"""B5: mentioning a running agent again catches it up on the conversation."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import api.v1.service.runs.invocation as invocation_service
from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.message import MessageType
from api.models.thread import Thread
from api.models.user import User
from api.permissions import MentionableSubjectType, ResourceType
from api.schemas.message import MessageMention, TextContent
from api.tests.factories import make_principal
from api.v1.service import access_rules
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.runs import resolution as run_resolution
from api.v1.service.runs import steering as steering_service
from api.v1.service.runs.bus import RunBusUnavailableError, RunSlotContendedError
from api.v1.service.runs.failures import RunFailureReason, classify_failure
from api.v1.service.runs.status import (
	AgentSlot,
	AwaitPendingRun,
	CatchUpAlreadyAccepted,
	CatchUpReserved,
	RunStore,
	StartNewRun,
	SteerExistingRun,
	agent_slots,
	run_conversations,
	run_inbox,
	run_registry,
)
from api.v1.service.runs.steering import InvocationCatchUp
from api.v1.service.threads.drafts import MessageDraft
from nokodo_ai.messages import TextContent as SDKTextContent
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.utils.typeid import TypeID, new_typeid


def test_access_change_has_explicit_failure_reason() -> None:
	assert classify_failure("access changed") is RunFailureReason.ACCESS_CHANGED


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
	thread = Thread(owner_id=owner.id, title="catch up")
	session.add(thread)
	await session.commit()
	await session.refresh(thread)
	return thread


async def _make_agent(session: AsyncSession, name: str, reader: User) -> Agent:
	agent = Agent(name=name)
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


async def _post(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	text: str,
	mentioned_agent_ids: list[TypeID] | None = None,
	message_type: MessageType = MessageType.USER,
	run_id: TypeID | None = None,
) -> TypeID:
	draft = MessageDraft(
		content=[TextContent(text=text)],
		type=message_type,
		sender_user_id=principal.user.id if message_type == MessageType.USER else None,
		mentions=[
			MessageMention(type=MentionableSubjectType.AGENT, id=agent_id)
			for agent_id in mentioned_agent_ids or []
		],
		metadata={"run_id": str(run_id)} if run_id is not None else {},
	)
	written = await thread_service.create_message(
		thread_id, draft, session, principal=principal
	)
	return written.message.id


def _texts(injection: InvocationCatchUp) -> list[str]:
	out: list[str] = []
	for message in injection.messages:
		if isinstance(message, SDKToolMessage):
			continue
		for part in message.content or []:
			if isinstance(part, SDKTextContent):
				out.append(part.text)
	return out


@pytest.mark.asyncio
async def test_mention_catches_the_run_up_on_what_it_missed(
	db_session: AsyncSession,
) -> None:
	"""the delta is everything since the run's last invocation, minus the
	run's own output, ending at the new mention."""
	owner = await _make_user(db_session, "catchup_owner")
	mate = await _make_user(db_session, "catchup_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	mate_principal = Principal.for_user(
		user=mate, group_ids=(), permissions=frozenset()
	)
	thread = await _make_thread(db_session, owner)
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD, thread.id, mate.id, db_session, level=AccessLevel.EDITOR
	)
	agent = await _make_agent(db_session, "catchup-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)
	await access_rules.grant_user_access_unchecked(
		ResourceType.AGENT,
		TypeID(str(agent.id)),
		mate.id,
		db_session,
		level=AccessLevel.READER,
	)

	run_id = TypeID(new_typeid("run"))
	invocation = await _post(
		db_session,
		thread.id,
		principal,
		"@agent investigate",
		mentioned_agent_ids=[TypeID(str(agent.id))],
	)
	await run_registry.start_run(
		run_id=run_id,
		agent_id=TypeID(str(agent.id)),
		user_id=owner.id,
		thread_id=TypeID(str(thread.id)),
	)
	try:
		await run_conversations.bind(
			run_id, container_root_id=None, invocation_message_id=invocation
		)
		# the run's own answer, plus conversation it never read.
		await _post(
			db_session,
			thread.id,
			principal,
			"answer chunk",
			message_type=MessageType.ASSISTANT,
			run_id=run_id,
		)
		await _post(db_session, thread.id, mate_principal, "use staging")
		await _post(db_session, thread.id, mate_principal, "postgres 17 only")
		re_mention = await _post(
			db_session,
			thread.id,
			mate_principal,
			"@agent did you see these",
			mentioned_agent_ids=[TypeID(str(agent.id))],
		)

		result = await steering_service.enqueue_run_invocation(
			run_id, re_mention, mate_principal, db_session
		)
		assert result.state == "queued"

		claimed = await run_inbox.claim_inbox(run_id)
		assert len(claimed) == 1
		catch_up = claimed[0]
		assert isinstance(catch_up, InvocationCatchUp)
		assert _texts(catch_up) == [
			"use staging",
			"postgres 17 only",
			"@agent did you see these",
		]
		# a catch-up is the server's own decision, so it owes no retraction.
		rs_mid = await run_registry.get_run(run_id)
		assert rs_mid is not None
		assert rs_mid.in_flight_steering == ()

		rs = await run_registry.get_run(run_id)
		assert rs is not None
		assert str(rs.queued_through_message_id) == str(re_mention)
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_catch_up_requires_a_mention_of_that_run_s_agent(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "catchupgate_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "gate-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	run_id = TypeID(new_typeid("run"))
	invocation = await _post(
		db_session,
		thread.id,
		principal,
		"@agent",
		mentioned_agent_ids=[TypeID(str(agent.id))],
	)
	plain = await _post(db_session, thread.id, principal, "just talking")
	await run_registry.start_run(
		run_id=run_id,
		agent_id=TypeID(str(agent.id)),
		user_id=owner.id,
		thread_id=TypeID(str(thread.id)),
	)
	try:
		await run_conversations.bind(
			run_id, container_root_id=None, invocation_message_id=invocation
		)
		with pytest.raises(HTTPException) as rejected:
			await steering_service.enqueue_run_invocation(
				run_id, plain, principal, db_session
			)
		assert rejected.value.status_code == 422
		rs = await run_registry.get_run(run_id)
		assert rs is not None
		# a rejected mention must not move the run's cursor.
		assert str(rs.queued_through_message_id) == str(invocation)
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_undelivered_catch_up_rewinds_the_cursor(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a batch the run refused is reported dropped, and its range is released.

	otherwise the cursor stays advanced over messages nobody ever delivered
	and the run is permanently blind to them.
	"""
	owner = await _make_user(db_session, "undelivered_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner)
	agent = await _make_agent(db_session, "undelivered-agent", owner)
	await thread_service.add_agents(
		db_session, principal, thread.id, [TypeID(str(agent.id))]
	)

	run_id = TypeID(new_typeid("run"))
	invocation = await _post(
		db_session,
		thread.id,
		principal,
		"@agent",
		mentioned_agent_ids=[TypeID(str(agent.id))],
	)
	await run_registry.start_run(
		run_id=run_id,
		agent_id=TypeID(str(agent.id)),
		user_id=owner.id,
		thread_id=TypeID(str(thread.id)),
	)
	try:
		await run_conversations.bind(
			run_id, container_root_id=None, invocation_message_id=invocation
		)
		re_mention = await _post(
			db_session,
			thread.id,
			principal,
			"@agent again",
			mentioned_agent_ids=[TypeID(str(agent.id))],
		)

		# the run ends between the reservation and the handoff.
		async def refuse(*_args: object, **_kwargs: object) -> bool:
			return False

		monkeypatch.setattr(run_inbox, "enqueue", refuse)

		result = await steering_service.enqueue_run_invocation(
			run_id, re_mention, principal, db_session
		)
		assert result.state == "dropped"

		rs = await run_registry.get_run(run_id)
		assert rs is not None
		assert str(rs.queued_through_message_id) == str(invocation)
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_ancestry_mismatch_releases_the_catch_up_reservation(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID("run_chain_mismatch")
	thread_id = TypeID("thread_chain_mismatch")
	agent_id = TypeID("agent_chain_mismatch")
	previous = TypeID("msg_previous")
	target = TypeID("msg_target")
	await run_registry.start_run(
		run_id=run_id,
		thread_id=thread_id,
		agent_id=agent_id,
		user_id=TypeID("user_chain_mismatch"),
	)
	await run_conversations.bind(run_id, None, previous)
	resolved = await run_resolution.find_run(run_id)
	assert resolved is not None

	async def canon_container(*_args: object) -> None:
		return None

	async def mismatched_chain(*_args: object) -> list[object]:
		raise ValueError("messages are not on the same conversation chain")

	monkeypatch.setattr(steering_service, "branch_root_id", canon_container)
	monkeypatch.setattr(steering_service, "messages_between", mismatched_chain)
	try:
		with pytest.raises(HTTPException) as conflict:
			await steering_service._enqueue_run_invocation(
				resolved,
				target,
				db_session,
			)
		assert conflict.value.status_code == 409
		after = await run_registry.get_run(run_id)
		assert after is not None
		assert after.queued_through_message_id == previous
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_older_invocation_covered_by_newer_cursor_is_delivered(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID("run_covered_invocation")
	thread_id = TypeID("thread_covered_invocation")
	older = TypeID("msg_older_invocation")
	newer = TypeID("msg_newer_invocation")
	await run_registry.start_run(
		run_id,
		TypeID("agent_covered_invocation"),
		TypeID("user_covered_invocation"),
		thread_id,
	)
	await run_conversations.bind(run_id, None, newer)

	async def canon_container(*_args: object) -> None:
		return None

	async def chain(
		_db: object,
		_thread_id: TypeID,
		after: TypeID | None,
		through: TypeID,
	) -> list[object]:
		if after == newer and through == older:
			raise ValueError("messages are not on the same conversation chain")
		if after == older and through == newer:
			return []
		raise AssertionError((after, through))

	monkeypatch.setattr(steering_service, "branch_root_id", canon_container)
	monkeypatch.setattr(steering_service, "messages_between", chain)
	try:
		resolved = await run_resolution.find_run(run_id)
		assert resolved is not None
		result = await steering_service._enqueue_run_invocation(
			resolved,
			older,
			db_session,
			accept_already_accepted=True,
		)
		assert result.state == "queued"
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_unanswered_invocation_distinguishes_never_started_from_undelivered(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a live run that would not take the message did not "never start".

	the failure is durable and shows in the thread forever, so telling readers
	the agent never started while it is answering right now is a lie.
	"""
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="unanswered")
	failures: list[tuple[RunFailureReason, TypeID | None]] = []

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append((reason, run_id))

	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)

	# nothing is running for this agent, and starting one fails.
	async def failing_launch(*_args: object, **_kwargs: object) -> TypeID:
		raise RuntimeError("no run for you")

	monkeypatch.setattr(invocation_service, "launch_invoked_run", failing_launch)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == [(RunFailureReason.NEVER_STARTED, None)]

	# now a run IS answering, but refuses the handoff.
	failures.clear()
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id=run_id, thread_id=thread_id, agent_id=agent_id, user_id=principal.user.id
	)
	await run_conversations.bind(
		run_id,
		container_root_id=None,
		invocation_message_id=None,
	)
	try:

		async def refuse(*_args: object, **_kwargs: object) -> bool:
			return False

		monkeypatch.setattr(invocation_service, "_steer", refuse)
		await invocation_service._answer_invocation(
			thread_id=thread_id,
			message_id=message_id,
			agent_id=agent_id,
			container_root_id=None,
			principal=principal,
			origin_session_id=None,
		)
	finally:
		await run_registry.complete_run(run_id)
	assert failures == [(RunFailureReason.NOT_DELIVERED, run_id)]


@pytest.mark.asyncio
async def test_invocation_startup_timeout_does_not_report_twice(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	failed_run_id = TypeID(new_typeid("run"))
	principal = make_principal(slug="startup-timeout")
	failures: list[RunFailureReason] = []

	async def timed_out(*_args: object, **_kwargs: object) -> TypeID:
		raise invocation_service.RunStartupError(failed_run_id)

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append(reason)

	monkeypatch.setattr(invocation_service, "launch_invoked_run", timed_out)
	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == []


@pytest.mark.asyncio
async def test_unregistered_invocation_startup_timeout_reports_never_started(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	failed_run_id = TypeID(new_typeid("run"))
	principal = make_principal(slug="unregistered-startup-timeout")
	failures: list[tuple[RunFailureReason, TypeID | None]] = []

	async def timed_out(*_args: object, **_kwargs: object) -> TypeID:
		raise invocation_service.RunStartupError(
			failed_run_id,
			run_registered=False,
		)

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append((reason, run_id))

	monkeypatch.setattr(invocation_service, "launch_invoked_run", timed_out)
	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == [(RunFailureReason.NEVER_STARTED, None)]


@pytest.mark.asyncio
async def test_pending_slot_timeout_without_run_id_is_not_delivered(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="pending-timeout")
	slot = AgentSlot(ready=asyncio.Event())
	failures: list[tuple[RunFailureReason, TypeID | None]] = []

	async def pending(*_args: object, **_kwargs: object) -> AwaitPendingRun:
		return AwaitPendingRun(slot=slot)

	async def timeout(_slot: AgentSlot) -> TypeID | None:
		raise TimeoutError

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append((reason, run_id))

	monkeypatch.setattr(agent_slots, "claim", pending)
	monkeypatch.setattr(agent_slots, "wait", timeout)
	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == [(RunFailureReason.NOT_DELIVERED, None)]


@pytest.mark.asyncio
async def test_unreachable_bus_reports_the_invocation_as_unavailable(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""an outage is not the agent failing to start; it is worth retrying.

	the caller already got its response, so this durable record is the only
	thing the thread will ever say about the attempt.
	"""
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="invocation-bus-outage")
	failures: list[tuple[RunFailureReason, TypeID | None]] = []

	async def unreachable(*_args: object, **_kwargs: object) -> object:
		raise RunBusUnavailableError("claim_run_slot")

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append((reason, run_id))

	monkeypatch.setattr(agent_slots, "claim", unreachable)
	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == [(RunFailureReason.UNAVAILABLE, None)]


@pytest.mark.asyncio
async def test_slot_contention_reports_the_message_as_undelivered(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""losing every race means a run IS starting, just not ours to steer.

	reporting "never started" here would tell the thread the agent is absent
	while another worker is starting it.
	"""
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="invocation-slot-contention")
	failures: list[tuple[RunFailureReason, TypeID | None]] = []

	async def contended(*_args: object, **_kwargs: object) -> object:
		raise RunSlotContendedError("nokodo-ai:run-slot:contended")

	async def capture(
		thread_id: TypeID,
		agent_id: TypeID,
		reason: RunFailureReason,
		anchor_message_id: TypeID | None = None,
		run_id: TypeID | None = None,
		partial_message_id: TypeID | None = None,
	) -> None:
		failures.append((reason, run_id))

	monkeypatch.setattr(agent_slots, "claim", contended)
	monkeypatch.setattr(invocation_service, "broadcast_run_failure", capture)
	await invocation_service._answer_invocation(
		thread_id=thread_id,
		message_id=message_id,
		agent_id=agent_id,
		container_root_id=None,
		principal=principal,
		origin_session_id=None,
	)
	assert failures == [(RunFailureReason.NOT_DELIVERED, None)]


@pytest.mark.asyncio
async def test_repeated_reservations_claim_disjoint_ranges() -> None:
	"""two mentions racing must not hand the agent the same messages twice."""
	store = RunStore()
	run_id = TypeID("run_reserve")
	await store.start_run(
		run_id=run_id,
		agent_id=TypeID("agent_reserve"),
		user_id=TypeID("user_reserve"),
		thread_id=TypeID("thread_reserve"),
	)
	await store.bind(
		run_id, container_root_id=None, invocation_message_id=TypeID("msg_1")
	)

	first = await store.reserve_catch_up(run_id, TypeID("msg_2"))
	second = await store.reserve_catch_up(run_id, TypeID("msg_3"))
	assert isinstance(first, CatchUpReserved)
	assert isinstance(second, CatchUpReserved)
	assert str(first.previous_invocation_id) == "msg_1"
	assert str(second.previous_invocation_id) == "msg_2"

	# the same mention twice is not a second range.
	repeat = await store.reserve_catch_up(run_id, TypeID("msg_3"))
	assert isinstance(repeat, CatchUpAlreadyAccepted)

	await store.release_catch_up(run_id, second)
	rs = await store.get_run(run_id)
	assert rs is not None
	assert str(rs.queued_through_message_id) == "msg_2"


@pytest.mark.asyncio
async def test_public_repeated_invocation_returns_conflict(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	run_id = TypeID(new_typeid("run"))
	thread_id = TypeID(new_typeid("thread"))
	agent_id = TypeID(new_typeid("agent"))
	message_id = TypeID(new_typeid("msg"))
	principal = make_principal(slug="repeat-invocation")
	await run_registry.start_run(
		run_id,
		agent_id,
		principal.user.id,
		thread_id,
	)
	await run_conversations.bind(run_id, None, message_id)

	async def allow(*_args: object, **_kwargs: object) -> None:
		return None

	async def mentions(*_args: object, **_kwargs: object) -> bool:
		return True

	async def canon(*_args: object, **_kwargs: object) -> None:
		return None

	monkeypatch.setattr(run_resolution, "require_thread_access", allow)
	monkeypatch.setattr(steering_service, "message_mentions_agent", mentions)
	monkeypatch.setattr(steering_service, "branch_root_id", canon)
	try:
		with pytest.raises(HTTPException) as conflict:
			await steering_service.enqueue_run_invocation(
				run_id,
				message_id,
				principal,
				db_session,
			)
		assert conflict.value.status_code == 409
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_stale_release_does_not_rewind_a_newer_reservation() -> None:
	"""an older batch failing must not re-ship what a newer one already claimed."""
	store = RunStore()
	run_id = TypeID("run_stale_release")
	await store.start_run(
		run_id=run_id,
		agent_id=TypeID("agent_stale"),
		user_id=TypeID("user_stale"),
		thread_id=TypeID("thread_stale"),
	)
	await store.bind(
		run_id, container_root_id=None, invocation_message_id=TypeID("msg_1")
	)

	first = await store.reserve_catch_up(run_id, TypeID("msg_2"))
	second = await store.reserve_catch_up(run_id, TypeID("msg_3"))
	assert isinstance(first, CatchUpReserved)
	assert isinstance(second, CatchUpReserved)

	# the FIRST batch fails after the second already moved the cursor past it.
	await store.release_catch_up(run_id, first)

	rs = await store.get_run(run_id)
	assert rs is not None
	assert str(rs.queued_through_message_id) == "msg_3"


@pytest.mark.asyncio
async def test_reply_anchor_is_consumed_once_per_snapshot() -> None:
	"""only the first answer of a block replies to the invocation; a later
	mention opens the next block."""
	store = RunStore()
	run_id = TypeID("run_anchor")
	await store.start_run(
		run_id=run_id,
		agent_id=TypeID("agent_anchor"),
		user_id=TypeID("user_anchor"),
		thread_id=TypeID("thread_anchor"),
	)
	await store.bind(
		run_id, container_root_id=None, invocation_message_id=TypeID("msg_1")
	)

	first = await store.reserve_reply_anchor(run_id)
	assert first is not None
	assert str(first.message_id) == "msg_1"
	assert await store.reserve_reply_anchor(run_id) is None
	await store.acknowledge_reply_anchor(run_id, first)

	await store.mark_catch_up_injected(run_id, TypeID("msg_4"))
	second = await store.reserve_reply_anchor(run_id)
	assert second is not None
	assert str(second.message_id) == "msg_4"
	await store.release_reply_anchor(run_id, second)
	retried = await store.reserve_reply_anchor(run_id)
	assert retried is not None
	assert retried.message_id == second.message_id


@pytest.mark.asyncio
async def test_active_run_lookup_is_scoped_to_agent_and_container() -> None:
	"""a mention steers the run answering ITS conversation, not any run that
	happens to be on the thread."""
	store = RunStore()
	thread_id = TypeID("thread_scope")
	canon_run = TypeID("run_canon")
	sub_run = TypeID("run_sub")
	agent_id = TypeID("agent_scope")

	await store.start_run(
		run_id=canon_run, agent_id=agent_id, user_id=TypeID("u"), thread_id=thread_id
	)
	await store.bind(canon_run, None, TypeID("msg_canon"))
	await store.start_run(
		run_id=sub_run, agent_id=agent_id, user_id=TypeID("u"), thread_id=thread_id
	)
	await store.bind(sub_run, TypeID("msg_root"), TypeID("msg_sub"))

	found_canon = await store.claim(thread_id, agent_id, None)
	found_sub = await store.claim(thread_id, agent_id, TypeID("msg_root"))
	assert found_canon == SteerExistingRun(run_id=canon_run)
	assert found_sub == SteerExistingRun(run_id=sub_run)

	other_agent = await store.claim(thread_id, TypeID("agent_other"), None)
	assert isinstance(other_agent, StartNewRun)


@pytest.mark.asyncio
async def test_unbound_run_does_not_claim_canon_invocation() -> None:
	store = RunStore()
	thread_id = TypeID("thread_unbound")
	agent_id = TypeID("agent_unbound")
	await store.start_run(
		run_id=TypeID("run_unbound"),
		agent_id=agent_id,
		user_id=TypeID("user_unbound"),
		thread_id=thread_id,
	)
	claim = await store.claim(thread_id, agent_id, None)
	assert isinstance(claim, StartNewRun)
