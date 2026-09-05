"""sub-thread service tests: writer count, placement, and scoped context."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.post_commit import run_post_commit_actions
from api.models.access_rule import AccessLevel
from api.models.agent import Agent
from api.models.group import Group, GroupMembership
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ActionPermission, ResourceType
from api.schemas.message import (
	MessageRange,
	MessageSplice,
	MessageUpdate,
	TextContent,
	ThreadLeaf,
)
from api.schemas.thread import ParticipantScope, ThreadListFilters
from api.tests.factories import principal_for
from api.v1.service import access_rules
from api.v1.service import threads as thread_service
from api.v1.service.authentication import Principal
from api.v1.service.authorization import resolve_resource_access_user_ids
from api.v1.service.threads.common import (
	is_multi_writer_thread,
	multi_writer_thread_ids,
)
from api.v1.service.threads.drafts import MessageDraft
from api.v1.service.threads.tree import (
	branch_root_id,
	load_message_branch,
)
from nokodo_ai.utils.typeid import TypeID, new_typeid


async def _make_user(session: AsyncSession, slug: str) -> User:
	user = User(
		email=f"{slug}@example.com",
		username=slug,
		hashed_password="password",
		is_active=True,
		is_superuser=False,
		preferences={},
		integration_tokens={},
		usage_quotas={},
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


async def _post(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	text: str,
	parent_id: TypeID | None = None,
) -> TypeID:
	draft = MessageDraft(
		content=[TextContent(text=text)],
		type=MessageType.USER,
		sender_user_id=principal.user.id,
	)
	if parent_id is not None:
		draft.splice = MessageSplice(parent_id=parent_id)
	written = await thread_service.create_message(
		thread_id, draft, session, principal=principal
	)
	return written.message.id


@pytest.mark.asyncio
async def test_generated_message_in_shared_thread_inherits_head(
	db_session: AsyncSession,
) -> None:
	from api.v1.service.chat.messages import prepare_generated_message
	from nokodo_ai.messages import UserMessage as SDKUserMessage

	owner = await _make_user(db_session, "subrun_owner")
	mate = await _make_user(db_session, "subrun_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "first run")
	thread_id = thread.id
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await db_session.commit()
	await run_post_commit_actions(db_session)

	prepared = prepare_generated_message(
		SDKUserMessage.from_text("hello agent"),
		sender_agent_id=None,
		run_id=TypeID(new_typeid("run")),
		citations=[],
		model_id=None,
	)
	message = (
		await thread_service.create_message(
			thread_id,
			prepared.draft,
			db_session,
			principal,
			originated_resources=prepared.originated_resources,
		)
	).message
	assert message.parent_id is None
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(message.id)

	# with a head present, a run without a parent continues from the head.
	prepared = prepare_generated_message(
		SDKUserMessage.from_text("still no leaf tracked"),
		sender_agent_id=None,
		run_id=TypeID(new_typeid("run")),
		citations=[],
		model_id=None,
	)
	follow_up = (
		await thread_service.create_message(
			thread_id,
			prepared.draft,
			db_session,
			principal,
			originated_resources=prepared.originated_resources,
		)
	).message
	assert str(follow_up.parent_id) == str(message.id)


@pytest.mark.asyncio
async def test_explicit_null_parent_roots_a_shared_sub_thread(
	db_session: AsyncSession,
) -> None:
	"""an explicit root sibling becomes a root-level sub-thread when shared."""
	owner = await _make_user(db_session, "subnull_owner")
	mate = await _make_user(db_session, "subnull_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "explicit null")
	thread_id = thread.id
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root_draft = MessageDraft(
		content=[TextContent(text="first")],
		type=MessageType.USER,
		sender_user_id=owner.id,
		splice=MessageSplice(parent_id=None),
	)
	root = (
		await thread_service.create_message(
			thread_id, root_draft, db_session, principal=principal
		)
	).message
	assert root.parent_id is None

	second_draft = MessageDraft(
		content=[TextContent(text="second root")],
		type=MessageType.USER,
		sender_user_id=owner.id,
		splice=MessageSplice(parent_id=None),
	)
	second = (
		await thread_service.create_message(
			thread_id, second_draft, db_session, principal=principal
		)
	).message
	assert second.parent_id is None
	assert second.branch_current_message_id == second.id
	await db_session.refresh(thread)
	assert thread.current_message_id == root.id


@pytest.mark.asyncio
async def test_explicit_thread_leaf_requires_manage_in_shared_thread(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "leaf_permission_owner")
	mate = await _make_user(db_session, "leaf_permission_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	manager = Principal.for_user(
		user=owner,
		group_ids=(),
		permissions=frozenset({ActionPermission.THREADS_MANAGE}),
	)
	thread = await _make_thread(db_session, owner, "leaf permission")
	thread_id = thread.id
	root = await _post(db_session, thread_id, principal, "root")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	draft = MessageDraft(
		content=[TextContent(text="select canon")],
		type=MessageType.USER,
		sender_user_id=owner.id,
		splice=MessageSplice(
			parent_id=root,
			leaf=ThreadLeaf(kind="thread"),
		),
	)
	with pytest.raises(HTTPException) as forbidden:
		await thread_service.create_message(
			thread_id,
			draft,
			db_session,
			principal=principal,
		)
	assert forbidden.value.status_code == 403
	await db_session.rollback()

	written = await thread_service.create_message(
		thread_id,
		draft,
		db_session,
		principal=manager,
	)
	stored_thread = await db_session.get(Thread, thread_id)
	assert stored_thread is not None
	assert stored_thread.current_message_id == written.message.id


@pytest.mark.asyncio
async def test_explicit_leaf_cannot_reparent_an_ancestor(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "cycle_guard_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	manager = Principal.for_user(
		user=owner,
		group_ids=(),
		permissions=frozenset({ActionPermission.THREADS_MANAGE}),
	)
	thread = await _make_thread(db_session, owner, "cycle guard")
	root = await _post(db_session, thread.id, principal, "root")
	child = await _post(db_session, thread.id, principal, "child")
	with pytest.raises(HTTPException) as conflict:
		await thread_service.create_message(
			thread.id,
			MessageDraft(
				content=[TextContent(text="cycle")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				splice=MessageSplice(
					parent_id=child,
					reparent_message_ids=[root],
					leaf=ThreadLeaf(kind="thread"),
				),
			),
			db_session,
			manager,
		)
	assert conflict.value.status_code == 409


@pytest.mark.asyncio
async def test_switch_branch_preserves_outgoing_canon_branch(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "switch_preserve_owner")
	mate = await _make_user(db_session, "switch_preserve_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	manager = Principal.for_user(
		user=owner,
		group_ids=(),
		permissions=frozenset({ActionPermission.THREADS_MANAGE}),
	)
	thread = await _make_thread(db_session, owner, "switch preserves canon")
	root = await _post(db_session, thread.id, principal, "root")
	outgoing_root = await _post(db_session, thread.id, principal, "outgoing root")
	outgoing_tail = await _post(db_session, thread.id, principal, "outgoing tail")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	incoming_root = await _post(
		db_session,
		thread.id,
		principal,
		"incoming root",
		parent_id=root,
	)
	incoming_tail = await _post(
		db_session,
		thread.id,
		principal,
		"incoming tail",
		parent_id=incoming_root,
	)

	await thread_service.switch_branch(
		thread.id,
		incoming_root,
		db_session,
		principal=manager,
	)
	outgoing = await db_session.get(Message, outgoing_root)
	incoming = await db_session.get(Message, incoming_root)
	assert outgoing is not None
	assert incoming is not None
	assert thread.current_message_id == incoming_tail
	assert outgoing.branch_current_message_id == outgoing_tail
	assert incoming.branch_current_message_id is None
	assert await thread_service.message_is_visible(
		db_session,
		thread.id,
		outgoing_tail,
	)


@pytest.mark.asyncio
async def test_concurrent_canon_sends_serialize(db_session: AsyncSession) -> None:
	"""simultaneous head sends chain instead of silently forking canon.

	runs with two independent sessions (real transactions) because the write
	lock is transaction-scoped - one shared session cannot express this race.
	"""
	from api.database.main import async_session_local
	from api.v1.service.authentication import load_principal_for_user

	owner = await _make_user(db_session, "subrace_owner")
	mate = await _make_user(db_session, "subrace_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "race")
	thread_id = thread.id
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	root = await _post(db_session, thread_id, principal, "root")

	async def _send(user_id: TypeID, text: str) -> tuple[str, str | None]:
		async with async_session_local() as session:
			sender = await load_principal_for_user(user_id, session)
			draft = MessageDraft(
				content=[TextContent(text=text)],
				type=MessageType.USER,
				sender_user_id=user_id,
			)
			written = await thread_service.create_message(
				thread_id, draft, session, principal=sender
			)
			message = written.message
			return str(message.id), str(message.parent_id)

	(first_id, first_parent), (second_id, second_parent) = await asyncio.gather(
		_send(owner.id, "from owner"),
		_send(mate.id, "from mate"),
	)

	# one linear chain: root <- first <- second, in either commit order.
	parents = {first_id: first_parent, second_id: second_parent}
	children_of_root = [mid for mid, pid in parents.items() if pid == str(root)]
	assert len(children_of_root) == 1
	chained = next(mid for mid in parents if mid != children_of_root[0])
	assert parents[chained] == children_of_root[0]
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == chained


@pytest.mark.asyncio
async def test_concurrent_sub_thread_replies_one_wins(
	db_session: AsyncSession,
) -> None:
	"""two racing replies to one anchor: one lands, the other 409s."""
	from api.database.main import async_session_local
	from api.v1.service.authentication import load_principal_for_user

	owner = await _make_user(db_session, "subrace2_owner")
	mate = await _make_user(db_session, "subrace2_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "race anchor")
	thread_id = thread.id
	anchor = await _post(db_session, thread_id, principal, "anchor")
	await _post(db_session, thread_id, principal, "head")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await db_session.commit()
	await run_post_commit_actions(db_session)

	async def _reply(user_id: TypeID, text: str) -> int:
		async with async_session_local() as session:
			sender = await load_principal_for_user(user_id, session)
			draft = MessageDraft(
				content=[TextContent(text=text)],
				type=MessageType.USER,
				sender_user_id=user_id,
				splice=MessageSplice(parent_id=anchor),
			)
			try:
				await thread_service.create_message(
					thread_id, draft, session, principal=sender
				)
			except HTTPException as exc:
				return exc.status_code
			return 201

	outcomes = sorted(
		await asyncio.gather(
			_reply(owner.id, "reply a"),
			_reply(mate.id, "reply b"),
		)
	)
	assert outcomes == [201, 409]


@pytest.mark.asyncio
async def test_writer_count_decides_the_thread_mode(db_session: AsyncSession) -> None:
	"""a reader share stays single-writer; an editor share does not."""
	owner = await _make_user(db_session, "subwriter_owner")
	reader = await _make_user(db_session, "subwriter_reader")
	editor = await _make_user(db_session, "subwriter_editor")
	thread = await _make_thread(db_session, owner, "writers")
	thread_id = thread.id

	assert await is_multi_writer_thread(db_session, thread_id) is False

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		reader.id,
		db_session,
		level=AccessLevel.READER,
	)
	assert await is_multi_writer_thread(db_session, thread_id) is False

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		editor.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	assert await is_multi_writer_thread(db_session, thread_id) is True

	# a downgrade re-levels the subject's one rule and flips the mode back.
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		editor.id,
		db_session,
		level=AccessLevel.READER,
	)
	assert await is_multi_writer_thread(db_session, thread_id) is False

	# stacked same-subject rules cannot exist: every write surface dedupes.
	from api.schemas.access_rule import AccessRuleCreate

	with pytest.raises(HTTPException) as stacked:
		await access_rules.set_access_rules_unchecked(
			ResourceType.THREAD,
			thread_id,
			[
				AccessRuleCreate(
					subject_user_id=editor.id,
					level=AccessLevel.EDITOR,
					order_index=0,
				),
				AccessRuleCreate(
					subject_user_id=editor.id,
					level=AccessLevel.READER,
					order_index=1,
				),
			],
			db_session,
		)
	assert stacked.value.status_code == 409


async def _scope_ids(
	session: AsyncSession,
	owner: User,
	scope: ParticipantScope,
) -> set[TypeID]:
	"""thread ids the owner sees under one participant scope."""
	threads = await thread_service.list_threads(
		session,
		principal_for(owner),
		filters=ThreadListFilters(participant_scope=scope),
		limit=100,
	)
	return {thread.id for thread in threads}


async def _assert_scope(
	session: AsyncSession,
	owner: User,
	thread_id: TypeID,
	people: bool,
) -> None:
	"""the listing scope and the per-thread check must never disagree."""
	assert await is_multi_writer_thread(session, thread_id) is people
	assert (thread_id in await _scope_ids(session, owner, "people")) is people
	assert (thread_id in await _scope_ids(session, owner, "solo")) is not people
	assert thread_id in await _scope_ids(session, owner, "all")


@pytest.mark.asyncio
async def test_participant_scope_counts_writers_not_shares(
	db_session: AsyncSession,
) -> None:
	"""scope follows the writer count: readers and agents never make people."""
	owner = await _make_user(db_session, "scope_owner")
	reader = await _make_user(db_session, "scope_reader")
	editor = await _make_user(db_session, "scope_editor")

	solo = await _make_thread(db_session, owner, "solo")
	await _assert_scope(db_session, owner, solo.id, people=False)

	# an agent in the room is not a user: presence never adds a writer.
	agent = Agent(name=f"scope agent {solo.id}", plugin_ids=[], config={})
	db_session.add(agent)
	await db_session.commit()
	db_session.add(ThreadParticipant(thread_id=solo.id, agent_id=agent.id))
	await db_session.commit()
	await _assert_scope(db_session, owner, solo.id, people=False)

	shared = await _make_thread(db_session, owner, "shared read-only")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		shared.id,
		reader.id,
		db_session,
		level=AccessLevel.READER,
	)
	await _assert_scope(db_session, owner, shared.id, people=False)

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		shared.id,
		editor.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await _assert_scope(db_session, owner, shared.id, people=True)


@pytest.mark.asyncio
async def test_participant_scope_resolves_group_shares_through_members(
	db_session: AsyncSession,
) -> None:
	"""a group rule counts its members, and only at editor or above."""
	owner = await _make_user(db_session, "group_scope_owner")
	member = await _make_user(db_session, "group_scope_member")
	empty_group = Group(name=f"empty {owner.id}", owner_id=owner.id)
	group = Group(name=f"crew {owner.id}", owner_id=owner.id)
	db_session.add_all([empty_group, group])
	await db_session.commit()
	db_session.add(GroupMembership(group_id=group.id, user_id=member.id))
	await db_session.commit()

	thread = await _make_thread(db_session, owner, "group share")
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		group.id,
		db_session,
		level=AccessLevel.READER,
	)
	await _assert_scope(db_session, owner, thread.id, people=False)

	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		group.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await _assert_scope(db_session, owner, thread.id, people=True)

	# an editor rule for a group nobody is in adds no writer.
	empty = await _make_thread(db_session, owner, "empty group share")
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		empty.id,
		empty_group.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await _assert_scope(db_session, owner, empty.id, people=False)


@pytest.mark.asyncio
async def test_writer_ids_agree_between_sql_and_python(
	db_session: AsyncSession,
) -> None:
	"""the listing subquery and the per-user resolver read the same rules."""
	owner = await _make_user(db_session, "agree_owner")
	editor = await _make_user(db_session, "agree_editor")
	reader = await _make_user(db_session, "agree_reader")
	thread = await _make_thread(db_session, owner, "agreement")
	other = await _make_thread(db_session, editor, "elsewhere")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		editor.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		reader.id,
		db_session,
		level=AccessLevel.READER,
	)

	writers = await resolve_resource_access_user_ids(
		ResourceType.THREAD,
		thread.id,
		db_session,
		required_level=AccessLevel.EDITOR,
	)
	assert set(writers) == {owner.id, editor.id}
	assert await is_multi_writer_thread(db_session, thread.id) is True
	# a second thread must not leak its writers into the first one's count.
	assert await is_multi_writer_thread(db_session, other.id) is False
	assert await multi_writer_thread_ids(db_session, [thread.id, other.id]) == {
		str(thread.id)
	}


@pytest.mark.asyncio
async def test_writer_model_conversion_waits_for_active_runs(
	db_session: AsyncSession,
) -> None:
	from api.v1.service import event_bus
	from api.v1.service.runs import access as _run_access
	from api.v1.service.runs.status import run_conversations, run_registry

	event_bus.register_server_event_handler(
		"access.updated",
		_run_access.handle_access_updated,
	)

	owner = await _make_user(db_session, "conversion_gate_owner")
	editor = await _make_user(db_session, "conversion_gate_editor")
	thread = await _make_thread(db_session, owner, "conversion gate")
	thread_id = thread.id
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread_id,
	)
	await run_conversations.bind(
		run_id,
		None,
		None,
	)
	try:
		await access_rules.grant_user_access_unchecked(
			ResourceType.THREAD,
			thread_id,
			editor.id,
			db_session,
			level=AccessLevel.EDITOR,
		)
		await db_session.commit()
		await run_post_commit_actions(db_session)
		assert await is_multi_writer_thread(db_session, thread_id)
		for _attempt in range(50):
			if await run_registry.get_run(run_id) is None:
				break
			await asyncio.sleep(0)
		assert await run_registry.get_run(run_id) is None
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_reader_acl_update_leaves_an_active_run_alone(
	db_session: AsyncSession,
) -> None:
	"""adding a reader does not abort an answer in progress.

	the writer model picks the topology, and a reader is a spectator - it does
	not change it. terminating here would let routine membership churn abort
	answers and write durable failures for a change that only widened access.
	"""
	from api.v1.service import event_bus
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs import access_cursors
	from api.v1.service.runs.status import run_registry

	owner = await _make_user(db_session, "reader_update_owner")
	reader = await _make_user(db_session, "reader_update_reader")
	thread = await _make_thread(db_session, owner, "reader update")
	run_id = TypeID(new_typeid("run"))
	event_bus.register_server_event_handler(
		"access.updated",
		run_access.handle_access_updated,
	)
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	try:
		await access_rules.grant_user_access_unchecked(
			ResourceType.THREAD,
			thread.id,
			reader.id,
			db_session,
			level=AccessLevel.READER,
		)
		await db_session.commit()
		await run_post_commit_actions(db_session)
		assert await run_registry.get_run(run_id) is not None
		# the revision was reconciled rather than ignored, so the next replay
		# does not re-read it.
		assert access_cursors.access_revision_cursor(thread.id) > 0
	finally:
		access_cursors.drop_access_revision_cursor(thread.id)
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_revoked_reader_is_detached_while_the_run_keeps_going(
	db_session: AsyncSession,
) -> None:
	"""losing access ends your view of the answer, not the answer itself.

	access is resolved once when a stream attaches, so without this a reader
	revoked mid-run keeps receiving a conversation they can no longer open.
	"""
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs import access_cursors
	from api.v1.service.runs.status import run_registry, run_streams

	owner = await _make_user(db_session, "detach_owner")
	revoked = await _make_user(db_session, "detach_revoked")
	kept = await _make_user(db_session, "detach_kept")
	thread = await _make_thread(db_session, owner, "detach")
	for user in (revoked, kept):
		await access_rules.grant_user_access_unchecked(
			ResourceType.THREAD,
			thread.id,
			user.id,
			db_session,
			level=AccessLevel.READER,
		)
	await db_session.commit()

	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	try:
		attached = {
			user.id: await run_streams.subscribe(run_id, user.id)
			for user in (revoked, kept)
		}
		assert all(subscription is not None for subscription in attached.values())

		await access_rules.revoke_user_access_unchecked(
			ResourceType.THREAD,
			thread.id,
			revoked.id,
			db_session,
		)
		await db_session.commit()
		access_cursors.set_access_revision_cursor(thread.id, 0)
		await run_access.replay_thread_acl_updates(thread.id)

		# the run is untouched: the other reader is still being served.
		assert await run_registry.get_run(run_id) is not None

		revoked_subscription = attached[revoked.id]
		assert revoked_subscription is not None
		# a terminal sentinel, not a hang: the stream ends the way one does.
		assert revoked_subscription[1].get_nowait() is None

		kept_subscription = attached[kept.id]
		assert kept_subscription is not None
		await run_streams.publish(run_id, b"event: delta\ndata: {}\n\n")
		assert kept_subscription[1].get_nowait() == b"event: delta\ndata: {}\n\n"
	finally:
		access_cursors.drop_access_revision_cursor(thread.id)
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_widening_access_detaches_nobody(db_session: AsyncSession) -> None:
	"""a new reader is not a reason to end anyone else's stream."""
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs import access_cursors
	from api.v1.service.runs.status import run_registry, run_streams

	owner = await _make_user(db_session, "widen_owner")
	newcomer = await _make_user(db_session, "widen_newcomer")
	thread = await _make_thread(db_session, owner, "widen")
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	try:
		subscription = await run_streams.subscribe(run_id, owner.id)
		assert subscription is not None

		await access_rules.grant_user_access_unchecked(
			ResourceType.THREAD,
			thread.id,
			newcomer.id,
			db_session,
			level=AccessLevel.READER,
		)
		await db_session.commit()
		access_cursors.set_access_revision_cursor(thread.id, 0)
		await run_access.replay_thread_acl_updates(thread.id)

		assert await run_registry.get_run(run_id) is not None
		await run_streams.publish(run_id, b"event: delta\ndata: {}\n\n")
		assert subscription[1].get_nowait() == b"event: delta\ndata: {}\n\n"
	finally:
		access_cursors.drop_access_revision_cursor(thread.id)
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_thread_deleted_event_terminates_local_runs(
	db_session: AsyncSession,
) -> None:
	"""thread.deleted terminates every local run for its thread."""
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs.status import run_registry

	owner = await _make_user(db_session, "deleted_event_owner")
	thread = await _make_thread(db_session, owner, "deleted event")
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	try:
		await run_access.handle_thread_deleted(
			{"type": "thread.deleted", "data": {"id": str(thread.id)}}
		)
		assert await run_registry.get_run(run_id) is None
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_reconnect_terminates_runs_for_soft_deleted_threads(
	db_session: AsyncSession,
) -> None:
	"""reconnect reconciliation terminates runs whose thread is deleted."""
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs.status import run_registry

	owner = await _make_user(db_session, "deleted_reconnect_owner")
	thread = await _make_thread(db_session, owner, "deleted reconnect")
	thread.soft_delete()
	await db_session.commit()
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	try:
		await run_access.replay_local_thread_acl_updates()
		assert await run_registry.get_run(run_id) is None
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_access_replay_terminates_all_runs_after_writer_transition(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from unittest.mock import AsyncMock

	from api.v1.service import access_rules as access_rule_service
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs.status import run_registry

	owner = await _make_user(db_session, "replay_owner")
	reader = await _make_user(db_session, "replay_reader")
	editor = await _make_user(db_session, "replay_editor")
	thread = await _make_thread(db_session, owner, "ACL replay")
	monkeypatch.setattr(access_rule_service, "fanout_event", AsyncMock())

	before_run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		before_run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	await access_rule_service.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		reader.id,
		db_session,
		level=AccessLevel.READER,
	)
	await access_rule_service.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		editor.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	after_run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		after_run_id,
		TypeID(new_typeid("agent")),
		owner.id,
		thread.id,
	)
	reader_two = await _make_user(db_session, "replay_reader_two")
	await access_rule_service.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		reader_two.id,
		db_session,
		level=AccessLevel.READER,
	)

	try:
		from api.v1.service.runs import access_cursors

		access_cursors.set_access_revision_cursor(thread.id, 0)
		await run_access.replay_thread_acl_updates(thread.id)
		assert await run_registry.get_run(before_run_id) is None
		assert await run_registry.get_run(after_run_id) is None
	finally:
		access_cursors.drop_access_revision_cursor(thread.id)
		await run_registry.complete_run(before_run_id)
		await run_registry.complete_run(after_run_id)


@pytest.mark.asyncio
async def test_access_revision_gap_terminates_local_runs(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	from api.v1.service.runs import access as run_access
	from api.v1.service.runs.status import run_registry

	thread_id = TypeID(new_typeid("thread"))
	run_id = TypeID(new_typeid("run"))
	await run_registry.start_run(
		run_id,
		TypeID(new_typeid("agent")),
		TypeID(new_typeid("user")),
		thread_id,
	)
	terminated: list[TypeID] = []

	async def revision_gap(*_args: object, **_kwargs: object) -> object:
		raise RuntimeError("access revision gap for thread")

	async def terminate(terminated_thread_id: TypeID) -> None:
		terminated.append(terminated_thread_id)

	monkeypatch.setattr(run_access, "read_access_change_batch", revision_gap)
	monkeypatch.setattr(run_access, "terminate_local_thread_runs", terminate)
	try:
		await run_access.replay_thread_acl_updates(thread_id)
		assert terminated == [thread_id]
	finally:
		await run_registry.complete_run(run_id)


@pytest.mark.asyncio
async def test_group_rule_counts_as_multi_writer(db_session: AsyncSession) -> None:
	"""a group editor rule counts users who resolve through membership."""
	from api.models.group import Group, GroupMembership

	owner = await _make_user(db_session, "subgroup_owner")
	member = await _make_user(db_session, "subgroup_member")
	thread = await _make_thread(db_session, owner, "group share")
	thread_id = thread.id
	group = Group(name="crew", owner_id=owner.id)
	db_session.add(group)
	await db_session.flush()
	db_session.add(GroupMembership(group_id=group.id, user_id=member.id))
	await db_session.commit()
	await db_session.refresh(group)

	assert await is_multi_writer_thread(db_session, thread_id) is False
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		group.id,
		db_session,
	)
	assert await is_multi_writer_thread(db_session, thread_id) is True


@pytest.mark.asyncio
async def test_empty_group_rule_stays_single_writer(db_session: AsyncSession) -> None:
	"""a group rule counts only when another user resolves through it."""
	from api.models.group import Group

	owner = await _make_user(db_session, "empty_group_owner")
	thread = await _make_thread(db_session, owner, "empty group")
	group = Group(name="empty crew", owner_id=owner.id)
	db_session.add(group)
	await db_session.commit()
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		group.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	assert await is_multi_writer_thread(db_session, thread.id) is False


@pytest.mark.asyncio
async def test_group_membership_emits_writer_model_access_facet(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""indirect resolved-access changes enrich the canonical access event."""
	from unittest.mock import AsyncMock

	from sqlalchemy import select

	from api.models.event import Event
	from api.models.event_types import EventType
	from api.models.group import Group
	from api.schemas.group import GroupMembershipCreate
	from api.v1.service import groups as group_service

	owner = await _make_user(db_session, "facet_owner")
	member = await _make_user(db_session, "facet_member")
	thread = await _make_thread(db_session, owner, "facet thread")
	group = Group(name="facet group", owner_id=owner.id)
	db_session.add(group)
	await db_session.commit()
	await access_rules.grant_group_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		group.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	monkeypatch.setattr(group_service, "fanout_event", AsyncMock())
	await group_service.add_member(
		group.id,
		GroupMembershipCreate(user_id=member.id),
		db_session,
		principal=principal_for(owner),
	)
	event = await db_session.scalar(
		select(Event)
		.where(
			Event.type == EventType.ACCESS_UPDATED,
			Event.scope_id == thread.id,
		)
		.order_by(Event.resource_revision.desc())
	)
	assert event is not None
	assert event.data["changes"] == []
	assert event.message_id == thread.current_message_id
	assert event.public_metadata["thread.writer_model.multi_writer"] == {
		"before": False,
		"after": True,
	}


@pytest.mark.asyncio
async def test_project_editor_access_makes_thread_multi_writer(
	db_session: AsyncSession,
) -> None:
	"""thread writer mode includes editor access inherited from projects."""
	from sqlalchemy import insert

	from api.models.many_to_many import thread_project_association
	from api.models.project import Project

	owner = await _make_user(db_session, "project_writer_owner")
	editor = await _make_user(db_session, "project_writer_editor")
	project = Project(name="shared project", owner_id=owner.id)
	thread = await _make_thread(db_session, owner, "project writers")
	db_session.add_all([project, thread])
	await db_session.flush()
	await db_session.execute(
		insert(thread_project_association).values(
			thread_id=thread.id,
			project_id=project.id,
		)
	)
	await db_session.commit()
	await access_rules.grant_user_access_unchecked(
		ResourceType.PROJECT,
		project.id,
		editor.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	assert await is_multi_writer_thread(db_session, thread.id) is True


@pytest.mark.asyncio
async def test_solo_thread_keeps_plain_branching(db_session: AsyncSession) -> None:
	"""one writer keeps the classic fork ux: a fork moves canon with it."""
	owner = await _make_user(db_session, "subsolo_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "solo")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "hello")
	await _post(db_session, thread_id, principal, "second")
	fork = await _post(db_session, thread_id, principal, "fork", parent_id=first)

	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(fork)
	assert await branch_root_id(db_session, thread_id, fork) is None


@pytest.mark.asyncio
async def test_reply_anchor_never_changes_placement_in_either_mode(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "subreply_owner")
	mate = await _make_user(db_session, "subreply_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "reply placement")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "first")
	solo_head = await _post(db_session, thread_id, principal, "solo head")
	solo_reply = (
		await thread_service.create_message(
			thread_id,
			MessageDraft(
				content=[TextContent(text="solo reply")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				reply_to_message_id=first,
			),
			db_session,
			principal=principal,
		)
	).message
	assert solo_reply.parent_id == solo_head
	assert solo_reply.reply_to_message_id == first

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	shared_head = await _post(db_session, thread_id, principal, "shared head")
	shared_reply = (
		await thread_service.create_message(
			thread_id,
			MessageDraft(
				content=[TextContent(text="shared reply")],
				type=MessageType.USER,
				sender_user_id=owner.id,
				reply_to_message_id=first,
			),
			db_session,
			principal=principal,
		)
	).message
	assert shared_reply.parent_id == shared_head
	assert shared_reply.reply_to_message_id == first


@pytest.mark.asyncio
async def test_user_message_edits_are_in_place_in_either_mode(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "subeditmode_owner")
	mate = await _make_user(db_session, "subeditmode_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "edit modes")
	thread_id = thread.id

	solo_message_id = await _post(db_session, thread_id, principal, "solo original")
	await thread_service.update_user_message(
		thread_id,
		solo_message_id,
		MessageUpdate(content="solo edited"),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	assert thread.current_message_id == solo_message_id

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	shared_message_id = await _post(db_session, thread_id, principal, "shared original")
	await thread_service.update_user_message(
		thread_id,
		shared_message_id,
		MessageUpdate(content="shared edited"),
		db_session,
		principal=principal,
	)
	await db_session.refresh(thread)
	assert thread.current_message_id == shared_message_id


@pytest.mark.asyncio
async def test_sub_threads_chain_and_never_move_canon(
	db_session: AsyncSession,
) -> None:
	"""in a shared thread a fork is a sub-thread; replies at its leaf extend
	its chain and never move canon."""
	owner = await _make_user(db_session, "subnest_owner")
	mate = await _make_user(db_session, "subnest_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "shared")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "hello")
	head = await _post(db_session, thread_id, principal, "second")

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root = await _post(db_session, thread_id, principal, "re: hello", parent_id=first)
	nested = await _post(db_session, thread_id, principal, "deeper", parent_id=root)
	deepest = await _post(db_session, thread_id, principal, "deepest", parent_id=nested)

	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(head)

	# every message under the anchor resolves to the same sub-thread root.
	for message_id in (root, nested, deepest):
		assert await branch_root_id(db_session, thread_id, message_id) == str(root)
	assert await branch_root_id(db_session, thread_id, head) is None

	# an off-canon anchor pages ONLY the sub-thread chain, not the canon prefix.
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		anchor_message_id=nested,
	)
	assert page.total == 3
	assert [str(m.id) for m in page.messages] == [str(root), str(nested), str(deepest)]
	assert not page.has_toward_root
	assert not page.has_toward_leaf


@pytest.mark.asyncio
async def test_one_sub_thread_per_anchor(db_session: AsyncSession) -> None:
	"""a message hosts a single sub-thread, at every level of the tree."""
	owner = await _make_user(db_session, "subone_owner")
	mate = await _make_user(db_session, "subone_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "one per anchor")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "hello")
	await _post(db_session, thread_id, principal, "second")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root = await _post(db_session, thread_id, principal, "re: hello", parent_id=first)
	await _post(db_session, thread_id, principal, "chained", parent_id=root)

	with pytest.raises(HTTPException) as second_sub:
		await _post(db_session, thread_id, principal, "another", parent_id=first)
	assert second_sub.value.status_code == 409

	# the first reply off root's chain nests; a second one on the same anchor
	# hits the same one-per-anchor rule.
	await _post(db_session, thread_id, principal, "nested", parent_id=root)
	with pytest.raises(HTTPException) as second_nested:
		await _post(db_session, thread_id, principal, "nested again", parent_id=root)
	assert second_nested.value.status_code == 409


@pytest.mark.asyncio
async def test_replying_off_a_chain_leaf_nests_a_sub_thread(
	db_session: AsyncSession,
) -> None:
	"""the placement rule recurses: posting at a container's leaf extends it,
	posting anywhere else roots a sub-thread inside that container."""
	owner = await _make_user(db_session, "subnested_owner")
	mate = await _make_user(db_session, "subnested_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "nesting")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	head = await _post(db_session, thread_id, principal, "two")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	# canon 1 -> 2, sub-thread rooted at 5 under 1, chain 5 -> 6 -> 7.
	root = await _post(db_session, thread_id, principal, "five", parent_id=first)
	middle = await _post(db_session, thread_id, principal, "six", parent_id=root)
	leaf = await _post(db_session, thread_id, principal, "seven", parent_id=middle)

	root_row = await db_session.get(Message, root)
	assert root_row is not None
	assert str(root_row.branch_current_message_id) == str(leaf)

	# 8 parents to 6, which is not the chain's leaf: it nests.
	nested_root = await _post(db_session, thread_id, principal, "8", parent_id=middle)
	nested_leaf = await _post(
		db_session, thread_id, principal, "9", parent_id=nested_root
	)

	nested_row = await db_session.get(Message, nested_root)
	assert nested_row is not None
	assert str(nested_row.branch_current_message_id) == str(nested_leaf)

	# the outer chain is untouched, and canon never moved.
	await db_session.refresh(root_row)
	assert str(root_row.branch_current_message_id) == str(leaf)
	await db_session.refresh(thread)
	assert str(thread.current_message_id) == str(head)

	# containment resolves to the innermost sub-thread.
	assert await branch_root_id(db_session, thread_id, leaf) == str(root)
	assert await branch_root_id(db_session, thread_id, nested_leaf) == str(nested_root)

	# and the nested chain pages on its own, without the outer chain's prefix.
	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		anchor_message_id=nested_leaf,
	)
	assert [str(m.id) for m in page.messages] == [str(nested_root), str(nested_leaf)]
	assert page.total == 2

	# a run inside the nested sub-thread sees its anchor plus its own messages.
	context = await load_message_branch(db_session, thread_id, nested_leaf)
	assert [str(m.id) for m in context] == [
		str(middle),
		str(nested_root),
		str(nested_leaf),
	]


@pytest.mark.asyncio
async def test_sub_thread_context_is_anchor_plus_own_messages(
	db_session: AsyncSession,
) -> None:
	"""sub-thread ai sees its anchor and its own replies, nothing else."""
	owner = await _make_user(db_session, "subctx_owner")
	mate = await _make_user(db_session, "subctx_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "context")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "anchor")
	canon_tail = await _post(db_session, thread_id, principal, "canon tail")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root = await _post(db_session, thread_id, principal, "sub root", parent_id=first)
	leaf = await _post(db_session, thread_id, principal, "sub leaf", parent_id=root)

	context = await load_message_branch(db_session, thread_id, leaf)
	assert [str(m.id) for m in context] == [str(first), str(root), str(leaf)]
	assert str(canon_tail) not in {str(m.id) for m in context}

	# the run path narrows to that same scope when handed a sub-thread parent.
	_thread, branch = await thread_service.load_thread_with_branch(
		thread_id, db_session, principal=principal, parent_id=leaf
	)
	assert [str(m.id) for m in branch] == [str(first), str(root), str(leaf)]

	# a canon parent still loads the whole canon branch.
	_thread, canon = await thread_service.load_thread_with_branch(
		thread_id, db_session, principal=principal, parent_id=canon_tail
	)
	assert [str(m.id) for m in canon] == [str(first), str(canon_tail)]


@pytest.mark.asyncio
async def test_historical_add_messages_in_shared_thread_needs_no_operator(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""ordinary historical placement is not an operator action."""
	from api.v1.service.runs import launch as runs_service

	owner = await _make_user(db_session, "subgate_owner")
	mate = await _make_user(db_session, "subgate_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "gate")
	thread_id = thread.id
	first = await _post(db_session, thread_id, principal, "first")
	await _post(db_session, thread_id, principal, "head")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	captured: dict[str, object] = {}
	expected_run_id = TypeID(new_typeid("run"))

	async def _capture_start_run(**kwargs: object) -> TypeID:
		captured.update(kwargs)
		return expected_run_id

	monkeypatch.setattr(runs_service, "_start_run", _capture_start_run)
	run_id = await runs_service.launch_thread_run(
		db_session,
		thread_id,
		TypeID(new_typeid("agent")),
		principal,
		splice=MessageSplice(parent_id=first),
	)
	splice = captured["splice"]
	assert isinstance(splice, MessageSplice)
	assert splice.parent_id == first
	assert run_id == expected_run_id


@pytest.mark.asyncio
async def test_replacing_sub_thread_root_transfers_its_leaf(
	db_session: AsyncSession,
) -> None:
	owner = await _make_user(db_session, "replace_sub_owner")
	mate = await _make_user(db_session, "replace_sub_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "replace sub-thread")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	await _post(db_session, thread.id, principal, "canon head")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	old_run_id = TypeID(new_typeid("run"))
	old_root = MessageDraft(
		type=MessageType.ASSISTANT,
		content=[TextContent(text="old root")],
		metadata={"run_id": str(old_run_id)},
		splice=MessageSplice(parent_id=anchor),
	)
	old_root_message = (
		await thread_service.create_message(
			thread.id, old_root, db_session, principal=principal
		)
	).message
	old_tail = MessageDraft(
		type=MessageType.TOOL,
		content=[TextContent(text="old tail")],
		metadata={"run_id": str(old_run_id)},
		splice=MessageSplice(parent_id=old_root_message.id),
	)
	old_tail_message = (
		await thread_service.create_message(
			thread.id, old_tail, db_session, principal=principal
		)
	).message
	successor = await _post(
		db_session,
		thread.id,
		principal,
		"sub-thread successor",
		parent_id=old_tail_message.id,
	)
	new_id = TypeID(new_typeid("msg"))
	written = await thread_service.create_message(
		thread.id,
		MessageDraft(
			type=MessageType.ASSISTANT,
			content=[TextContent(text="new root")],
			metadata={"run_id": str(new_typeid("run"))},
			splice=MessageSplice(
				parent_id=anchor,
				reparent_message_ids=[successor],
				replaces=MessageRange(
					head_id=old_root_message.id,
					tail_id=old_tail_message.id,
				),
			),
		),
		db_session,
		principal,
		message_id=new_id,
	)
	replacement = written.message
	assert replacement.parent_id == anchor
	assert replacement.branch_current_message_id == successor
	successor_message = await db_session.get(Message, successor)
	assert successor_message is not None
	assert successor_message.parent_id == new_id
	assert await branch_root_id(db_session, thread.id, successor) == new_id


@pytest.mark.asyncio
async def test_replacing_sub_thread_root_loads_only_its_anchor_context(
	db_session: AsyncSession,
) -> None:
	from api.v1.service.chat.messages import load_sdk_thread_before_message
	from nokodo_ai.messages import TextContent as SDKTextContent
	from nokodo_ai.messages import UserMessage as SDKUserMessage

	owner = await _make_user(db_session, "replace_context_owner")
	mate = await _make_user(db_session, "replace_context_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "replace context")
	anchor = await _post(db_session, thread.id, principal, "anchor")
	canon_tail = await _post(db_session, thread.id, principal, "canon tail")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread.id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	root = MessageDraft(
		type=MessageType.ASSISTANT,
		content=[TextContent(text="old sub answer")],
		metadata={"run_id": str(new_typeid("run"))},
		splice=MessageSplice(parent_id=anchor),
	)
	root_message = (
		await thread_service.create_message(
			thread.id, root, db_session, principal=principal
		)
	).message
	context, predecessor_id = await load_sdk_thread_before_message(
		thread.id,
		root_message.id,
		db_session,
		principal,
	)
	assert predecessor_id == anchor
	assert len(context.messages) == 1
	anchor_message = context.messages[0]
	assert isinstance(anchor_message, SDKUserMessage)
	anchor_content = anchor_message.content[0]
	assert isinstance(anchor_content, SDKTextContent)
	assert anchor_content.text == "anchor"
	assert all(
		str(canon_tail) not in str(message.metadata) for message in context.messages
	)


@pytest.mark.asyncio
async def test_message_created_event_carries_sub_thread_root(
	db_session: AsyncSession,
) -> None:
	"""non-canon MESSAGE_CREATED events name the sub-thread root; canon events
	omit the key."""
	from sqlalchemy import select

	from api.models.event import Event
	from api.models.event_types import EventType

	owner = await _make_user(db_session, "subevent_owner")
	mate = await _make_user(db_session, "subevent_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "events")
	thread_id = thread.id
	first = await _post(db_session, thread_id, principal, "first")
	head = await _post(db_session, thread_id, principal, "head")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	root = await _post(db_session, thread_id, principal, "re: first", parent_id=first)
	chained = await _post(db_session, thread_id, principal, "more", parent_id=root)

	rows = (
		await db_session.execute(
			select(Event)
			.where(
				Event.thread_id == str(thread_id),
				Event.type == EventType.MESSAGE_CREATED,
			)
			.order_by(Event.created_at, Event.id)
		)
	).scalars()
	by_message = {str(event.message_id): event.data or {} for event in rows}
	assert by_message[str(head)]["splice"]["leaf"] == {"kind": "thread"}
	assert by_message[str(root)]["splice"]["leaf"] == {
		"kind": "branch",
		"root_id": str(root),
	}
	assert by_message[str(chained)]["splice"]["leaf"] == {
		"kind": "branch",
		"root_id": str(root),
	}


@pytest.mark.asyncio
async def test_deleting_a_chain_tail_re_points_the_sub_thread(
	db_session: AsyncSession,
) -> None:
	"""a deletion that takes the chain's leaf leaves the root pointing at the
	deepest message that survived, so the chain stays extendable."""
	owner = await _make_user(db_session, "subdel_owner")
	mate = await _make_user(db_session, "subdel_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "deletion")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	await _post(db_session, thread_id, principal, "two")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root = await _post(db_session, thread_id, principal, "sub root", parent_id=first)
	middle = await _post(db_session, thread_id, principal, "middle", parent_id=root)
	await _post(db_session, thread_id, principal, "leaf", parent_id=middle)

	await thread_service.delete_user_message_turn(
		thread_id, middle, db_session, principal=principal
	)

	root_row = await db_session.get(Message, root)
	assert root_row is not None
	await db_session.refresh(root_row)
	assert str(root_row.branch_current_message_id) == str(root)

	# the chain still accepts a reply at its (new) leaf.
	revived = await _post(db_session, thread_id, principal, "again", parent_id=root)
	await db_session.refresh(root_row)
	assert str(root_row.branch_current_message_id) == str(revived)


@pytest.mark.asyncio
async def test_pointerless_branches_are_invisible_once_shared(
	db_session: AsyncSession,
) -> None:
	"""a branch abandoned before the thread was shared carries no pointer, so
	it is not a sub-thread: a shared thread neither reads nor extends it."""
	owner = await _make_user(db_session, "sublegacy_owner")
	mate = await _make_user(db_session, "sublegacy_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "legacy")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	await _post(db_session, thread_id, principal, "two")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	root = await _post(db_session, thread_id, principal, "sub root", parent_id=first)
	leaf = await _post(db_session, thread_id, principal, "sub leaf", parent_id=root)

	# strip the pointer to reproduce a branch the owner forked away from while
	# the thread was still solo.
	root_row = await db_session.get(Message, root)
	assert root_row is not None
	root_row.branch_current_message_id = None
	await db_session.commit()

	with pytest.raises(HTTPException) as read:
		await thread_service.get_branch_page(
			thread_id,
			db_session,
			principal=principal,
			anchor_message_id=leaf,
		)
	assert read.value.status_code == 404
	listed = await thread_service.list_messages(
		thread_id,
		db_session,
		principal,
		limit=100,
	)
	assert leaf not in {message.id for message in listed}

	with pytest.raises(HTTPException) as run_write:
		await thread_service.create_message_at_run_tail(
			thread_id,
			MessageDraft(
				type=MessageType.ASSISTANT,
				content=[TextContent(text="hidden output")],
			),
			leaf,
			TypeID(new_typeid("run")),
			db_session,
			principal,
		)
	assert run_write.value.status_code == 409
	await db_session.rollback()

	with pytest.raises(HTTPException) as write:
		await _post(db_session, thread_id, principal, "next", parent_id=leaf)
	assert write.value.status_code == 404


@pytest.mark.asyncio
async def test_abandoned_stretch_is_readable_solo_and_hidden_once_shared(
	db_session: AsyncSession,
) -> None:
	"""solo branching leaves pointerless stretches behind. the owner can still
	page them; sharing the thread takes them out of the conversation."""
	owner = await _make_user(db_session, "subaband_owner")
	mate = await _make_user(db_session, "subaband_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "abandoned")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	stretch = await _post(db_session, thread_id, principal, "two")
	older = await _post(db_session, thread_id, principal, "older")
	await _post(db_session, thread_id, principal, "newer", parent_id=stretch)
	# forking off the first message abandons that whole stretch.
	await _post(db_session, thread_id, principal, "other", parent_id=first)

	solo_page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		anchor_message_id=older,
	)
	assert str(older) in [str(m.id) for m in solo_page.messages]

	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)

	with pytest.raises(HTTPException) as shared:
		await thread_service.get_branch_page(
			thread_id,
			db_session,
			principal=principal,
			anchor_message_id=older,
		)
	assert shared.value.status_code == 404


@pytest.mark.asyncio
async def test_branch_page_carries_siblings(db_session: AsyncSession) -> None:
	"""a page ships the branches hanging off its messages, so the client can
	show sub-threads (shared) or alternatives (solo) without walking the tree."""
	owner = await _make_user(db_session, "subsib_owner")
	mate = await _make_user(db_session, "subsib_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "siblings")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	await _post(db_session, thread_id, principal, "two")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	root = await _post(db_session, thread_id, principal, "sub", parent_id=first)

	page = await thread_service.get_branch_page(
		thread_id, db_session, principal=principal
	)
	assert [str(m.id) for m in page.siblings] == [str(root)]
	assert [(str(c.parent_id), c.total) for c in page.sibling_counts] == [
		(str(first), 1)
	]


@pytest.mark.asyncio
async def test_sibling_fanout_is_capped_and_pageable(
	db_session: AsyncSession,
) -> None:
	"""one message's alternatives cannot fill a page: past the cap the client
	is told the real count and pages the rest."""
	from api.v1.service.threads.branches import SIBLING_FANOUT_CAP

	owner = await _make_user(db_session, "subcap_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "cap")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	forks = [
		await _post(db_session, thread_id, principal, f"fork {i}", parent_id=first)
		for i in range(SIBLING_FANOUT_CAP + 3)
	]

	page = await thread_service.get_branch_page(
		thread_id, db_session, principal=principal, anchor_message_id=first
	)
	assert len(page.siblings) == SIBLING_FANOUT_CAP
	# the count is the TRUE one, so a fork is labelled without paging it.
	assert [item.total for item in page.sibling_counts] == [len(forks)]

	rest = await thread_service.list_message_siblings(
		thread_id,
		first,
		db_session,
		principal=principal,
		skip=SIBLING_FANOUT_CAP,
		limit=50,
	)
	assert rest
	paged = {str(m.id) for m in page.siblings} | {str(m.id) for m in rest}
	assert paged == set(map(str, forks))


@pytest.mark.asyncio
async def test_linear_conversation_reports_no_siblings(
	db_session: AsyncSession,
) -> None:
	"""a message's own continuation is not an alternative to it, so a chat
	with no forks carries no siblings and no counts."""
	owner = await _make_user(db_session, "sublinear_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "linear")
	thread_id = thread.id

	for index in range(4):
		await _post(db_session, thread_id, principal, f"m{index}")

	page = await thread_service.get_branch_page(
		thread_id, db_session, principal=principal
	)
	assert len(page.messages) == 4
	assert page.siblings == []
	assert page.sibling_counts == []


@pytest.mark.asyncio
async def test_demoted_thread_reads_whole_branches_again(
	db_session: AsyncSession,
) -> None:
	"""sub-threads exist only while a thread has two writers. dropping back to
	one writer restores plain branching, so a former sub-thread reads as an
	ordinary branch, root included, despite its leftover pointer."""
	owner = await _make_user(db_session, "subdemote_owner")
	mate = await _make_user(db_session, "subdemote_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "demote")
	thread_id = thread.id

	first = await _post(db_session, thread_id, principal, "one")
	await _post(db_session, thread_id, principal, "two")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	root = await _post(db_session, thread_id, principal, "sub", parent_id=first)
	leaf = await _post(db_session, thread_id, principal, "sub leaf", parent_id=root)

	await access_rules.set_access_rules_unchecked(
		ResourceType.THREAD, thread_id, [], db_session
	)
	assert await is_multi_writer_thread(db_session, thread_id) is False

	page = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		anchor_message_id=leaf,
	)
	assert [str(m.id) for m in page.messages] == [str(first), str(root), str(leaf)]


@pytest.mark.asyncio
async def test_branch_cursors_survive_concurrent_writes(
	db_session: AsyncSession,
) -> None:
	"""scrolling by cursor never repeats or skips a message when someone else
	writes mid-scroll; scrolling by offset shifts under the same write."""
	owner = await _make_user(db_session, "subcur_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "cursors")
	thread_id = thread.id

	for index in range(6):
		await _post(db_session, thread_id, principal, f"m{index}")

	first_page = await thread_service.get_branch_page(
		thread_id, db_session, principal=principal, limit=3
	)
	assert first_page.cursor_toward_root is not None

	# a new message lands at the leaf, shifting every offset by one.
	await _post(db_session, thread_id, principal, "interloper")

	resumed = await thread_service.get_branch_page(
		thread_id,
		db_session,
		principal=principal,
		limit=3,
		cursor=first_page.cursor_toward_root,
	)
	seen = [str(m.id) for m in first_page.messages]
	assert not set(seen) & {str(m.id) for m in resumed.messages}

	by_offset = await thread_service.get_branch_page(
		thread_id, db_session, principal=principal, skip=3, limit=3
	)
	assert set(seen) & {str(m.id) for m in by_offset.messages}


@pytest.mark.asyncio
async def test_deletion_that_reseats_canon_clears_pointers(
	db_session: AsyncSession,
) -> None:
	"""when a deletion re-seats the head onto what was a sub-thread, those
	messages are canon now and must stop claiming to root a sub-thread."""
	owner = await _make_user(db_session, "subreseat_owner")
	mate = await _make_user(db_session, "subreseat_mate")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "reseat")
	thread_id = thread.id

	await _post(db_session, thread_id, principal, "a")
	anchor = await _post(db_session, thread_id, principal, "b")
	await access_rules.grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		mate.id,
		db_session,
		level=AccessLevel.EDITOR,
	)
	tail = await _post(db_session, thread_id, principal, "c")
	root = await _post(db_session, thread_id, principal, "sub", parent_id=anchor)

	await thread_service.delete_user_message_turn(
		thread_id, tail, db_session, principal=principal
	)

	await db_session.refresh(thread)
	root_row = await db_session.get(Message, root)
	assert root_row is not None
	await db_session.refresh(root_row)
	# the head fell onto the sub-thread, which makes it canon.
	assert str(thread.current_message_id) == str(root)
	assert root_row.branch_current_message_id is None
	assert await branch_root_id(db_session, thread_id, root) is None


@pytest.mark.asyncio
async def test_editing_a_message_snapshots_prior_content(
	db_session: AsyncSession,
) -> None:
	"""in-place edits are auditable: the event carries what the message said."""
	from api.models.event_types import EventType
	from api.schemas.message import MessageUpdate

	owner = await _make_user(db_session, "subedit_owner")
	principal = Principal.for_user(user=owner, group_ids=(), permissions=frozenset())
	thread = await _make_thread(db_session, owner, "edits")
	thread_id = thread.id

	message_id = await _post(db_session, thread_id, principal, "original text")
	await thread_service.update_user_message(
		thread_id,
		message_id,
		MessageUpdate(content="corrected text"),
		db_session,
		principal=principal,
	)

	page = await thread_service.list_events_for_message_ids(
		thread_id,
		[message_id],
		db_session,
		principal=principal,
		event_types=[EventType.MESSAGE_UPDATED],
	)
	assert len(page.items) == 1
	previous = (page.items[0].data or {}).get("previous_content")
	assert isinstance(previous, list)
	assert [part.get("text") for part in previous] == ["original text"]
