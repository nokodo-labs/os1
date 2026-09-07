"""thread membership: who can access a thread (the ACL) + the read roster.

a "member" is an ACL subject - a human or a live group - granted access to a
thread. this module is the thread-facing wrapper over the standardized access
rule system: it adds friend-gating / the stranger-invite split and the durable
acl.* events that render membership changes inline, then delegates the actual
grant/revoke to ``access_rules``. removing a human member also clears that
user's now-orphaned per-thread state (delegated to ``user_state``).

it also owns the read side of membership: the thread roster is a projection of
the ACL (owner + access rules) plus agent presence, and the thread API payload
that embeds it. the roster carries identity + access level only (no private
state), so it stays user-agnostic and safe to cache across users.
"""

from collections.abc import Sequence

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.agent import Agent
from api.models.group import Group
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ResourceType
from api.schemas.agent import AgentSummary
from api.schemas.group import GroupSummary
from api.schemas.thread import Thread as ThreadOut
from api.schemas.thread_participant import (
	AgentThreadParticipant,
	GroupThreadParticipant,
	UserThreadParticipant,
)
from api.schemas.thread_participant import (
	ThreadParticipant as ThreadParticipantOut,
)
from api.schemas.user import UserSummary
from api.v1.service.access_rules import (
	grant_subject_access_batch_unchecked,
	revoke_group_access_unchecked,
	revoke_user_access_unchecked,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	AccessChangeEventEnrichment,
	AccessChangeFinalizer,
	ResolvedAccessShape,
	ResourceRef,
	project_private,
	register_access_change_hook,
	require_resource_access,
	require_thread_access,
)
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.social.friendship import are_friends, is_blocked
from api.v1.service.threads.common import (
	INVITE_PENDING,
	emit_thread_updated,
	load_membership_thread,
	message_load_options,
	message_payloads,
)
from api.v1.service.threads.user_state import (
	clear_participant_state,
	ensure_participant,
	sync_thread_state_vectors,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


async def _thread_writer_model_hook(
	resource_refs: list[ResourceRef],
	resolved_access: dict[ResourceRef, ResolvedAccessShape],
	session: AsyncSession,
) -> AccessChangeFinalizer:
	"""capture resolved thread writer models for access event metadata."""
	thread_ids = [
		resource_id
		for resource_type, resource_id in resource_refs
		if resource_type == ResourceType.THREAD
	]
	before = {
		thread_id: len(
			resolved_access[(ResourceType.THREAD, thread_id)].derived_writers
		)
		> 1
		for thread_id in thread_ids
	}

	async def finalize(
		session: AsyncSession,
		after_access: dict[ResourceRef, ResolvedAccessShape],
	) -> dict[ResourceRef, AccessChangeEventEnrichment]:
		"""return writer-model transitions for affected threads."""
		result: dict[ResourceRef, AccessChangeEventEnrichment] = {}
		after = {
			thread_id: len(
				after_access[(ResourceType.THREAD, thread_id)].derived_writers
			)
			> 1
			for thread_id in thread_ids
		}
		changed_thread_ids = [
			thread_id
			for thread_id, was_multi_writer in before.items()
			if was_multi_writer != after[thread_id]
		]
		message_rows = (
			await session.execute(
				select(Thread.id, Thread.current_message_id).where(
					Thread.id.in_(changed_thread_ids)
				)
			)
		).all()
		message_ids = {thread_id: message_id for thread_id, message_id in message_rows}
		for thread_id, was_multi_writer in before.items():
			is_multi_writer = after[thread_id]
			if was_multi_writer == is_multi_writer:
				continue
			metadata: JSONObject = {
				"thread.writer_model.multi_writer": {
					"before": was_multi_writer,
					"after": is_multi_writer,
				}
			}
			result[(ResourceType.THREAD, thread_id)] = AccessChangeEventEnrichment(
				metadata=metadata,
				message_id=message_ids.get(thread_id),
			)
		return result

	return finalize


register_access_change_hook(_thread_writer_model_hook)


# roster: the read side of membership (ACL + agent presence)


async def _summaries(
	session: AsyncSession,
	model: type[User] | type[Agent] | type[Group],
	ids: set[str],
) -> dict[str, User | Agent | Group]:
	if not ids:
		return {}
	rows = (
		(await session.execute(select(model).where(model.id.in_(list(ids)))))
		.scalars()
		.all()
	)
	return {str(row.id): row for row in rows}


async def build_rosters(
	session: AsyncSession,
	owner_by_thread: dict[str, str],
	thread_ids: list[TypeID] | list[str],
) -> dict[str, list[ThreadParticipantOut]]:
	"""compute the roster for several threads from the ACL + agent presence."""
	ids = [str(t) for t in thread_ids]
	rosters: dict[str, list[ThreadParticipantOut]] = {tid: [] for tid in ids}
	if not ids:
		return rosters

	rule_rows = (
		await session.execute(
			select(
				AccessRule.thread_id,
				AccessRule.subject_user_id,
				AccessRule.subject_group_id,
				AccessRule.level,
			).where(
				AccessRule.thread_id.in_(ids),
				or_(
					AccessRule.subject_user_id.is_not(None),
					AccessRule.subject_group_id.is_not(None),
				),
			)
		)
	).all()
	agent_rows = (
		await session.execute(
			select(
				ThreadParticipant.thread_id,
				ThreadParticipant.agent_id,
				ThreadParticipant.invoke_on_mention,
			).where(
				ThreadParticipant.thread_id.in_(ids),
				ThreadParticipant.agent_id.is_not(None),
			)
		)
	).all()

	user_ids = set(owner_by_thread.values())
	group_ids: set[str] = set()
	for _tid, user_id, group_id, _level in rule_rows:
		if user_id is not None:
			user_ids.add(str(user_id))
		if group_id is not None:
			group_ids.add(str(group_id))
	agent_ids = {str(aid) for _tid, aid, _invoke in agent_rows if aid is not None}

	users = await _summaries(session, User, user_ids)
	groups = await _summaries(session, Group, group_ids)
	agents = await _summaries(session, Agent, agent_ids)

	for tid in ids:
		entries: list[ThreadParticipantOut] = []
		seen_users: set[str] = set()
		owner_id = owner_by_thread.get(tid)
		owner_user = users.get(owner_id) if owner_id else None
		if owner_id and isinstance(owner_user, User):
			entries.append(
				UserThreadParticipant(
					id=TypeID(owner_id),
					thread_id=TypeID(tid),
					access_level=AccessLevel.ADMIN,
					is_owner=True,
					user=UserSummary.model_validate(owner_user),
				)
			)
			seen_users.add(owner_id)

		for rule_tid, user_id, group_id, level in rule_rows:
			if str(rule_tid) != tid:
				continue
			if user_id is not None:
				uid = str(user_id)
				summary = users.get(uid)
				if uid in seen_users or not isinstance(summary, User):
					continue
				seen_users.add(uid)
				entries.append(
					UserThreadParticipant(
						id=TypeID(uid),
						thread_id=TypeID(tid),
						access_level=level,
						user=UserSummary.model_validate(summary),
					)
				)
			elif group_id is not None:
				gid = str(group_id)
				group = groups.get(gid)
				if not isinstance(group, Group):
					continue
				entries.append(
					GroupThreadParticipant(
						id=TypeID(gid),
						thread_id=TypeID(tid),
						access_level=level,
						group=GroupSummary.model_validate(group),
					)
				)

		for agent_tid, agent_id, invoke_on_mention in agent_rows:
			if str(agent_tid) != tid or agent_id is None:
				continue
			agent = agents.get(str(agent_id))
			if not isinstance(agent, Agent):
				continue
			entries.append(
				AgentThreadParticipant(
					id=TypeID(str(agent_id)),
					thread_id=TypeID(tid),
					agent=AgentSummary.model_validate(agent),
					invoke_on_mention=invoke_on_mention,
				)
			)
		rosters[tid] = entries
	return rosters


async def build_roster(
	session: AsyncSession,
	thread_id: TypeID | str,
	owner_id: TypeID | str,
) -> list[ThreadParticipantOut]:
	"""compute the roster for a single thread (see ``build_rosters``)."""
	rosters = await build_rosters(session, {str(thread_id): str(owner_id)}, [thread_id])
	return rosters[str(thread_id)]


async def human_roster_labels(
	session: AsyncSession,
	thread_id: TypeID,
) -> dict[str, str]:
	"""return display labels for human entries in the canonical thread roster."""
	owner_id = await session.scalar(
		select(Thread.owner_id).where(Thread.id == thread_id)
	)
	if owner_id is None:
		return {}
	roster = await build_roster(session, thread_id, owner_id)
	return {
		str(participant.id): (
			participant.user.display_name
			or participant.user.username
			or str(participant.id)
		)
		for participant in roster
		if isinstance(participant, UserThreadParticipant)
	}


async def build_thread_payload(
	session: AsyncSession,
	thread: Thread,
) -> ThreadOut:
	"""build the API payload for a thread, resolving its ACL-computed roster.

	requires ``thread.projects`` to be loaded. the roster is user-agnostic
	(identity + access level, no private state), so the payload is safe to cache.
	"""
	payload = ThreadOut.from_row(thread)
	payload.participants = await build_roster(session, thread.id, thread.owner_id)
	return payload


async def build_thread_payloads(
	session: AsyncSession,
	threads: Sequence[Thread],
) -> list[ThreadOut]:
	"""build API payloads for a page of threads with one batched roster pass.

	the per-thread variant fires several queries each; listing endpoints must
	use this to resolve every roster for the page in a single ``build_rosters``
	call.
	"""
	if not threads:
		return []
	owner_by_thread = {str(t.id): str(t.owner_id) for t in threads}
	rosters = await build_rosters(session, owner_by_thread, [t.id for t in threads])
	payloads: list[ThreadOut] = []
	for thread in threads:
		payload = ThreadOut.from_row(thread)
		payload.participants = rosters[str(thread.id)]
		payloads.append(payload)
	return payloads


async def attach_last_messages(
	session: AsyncSession,
	threads: Sequence[Thread],
	payloads: list[ThreadOut],
	principal: Principal,
) -> None:
	"""set each payload's ``last_message`` from its thread's current message.

	the nested payload is projected here: ``project_private`` reaches only the
	top level of the thread it is given, so the message facet would otherwise
	ride along unprojected.
	"""
	message_ids = {t.current_message_id for t in threads if t.current_message_id}
	if not message_ids:
		return
	result = await session.execute(
		select(Message)
		.where(Message.id.in_(message_ids))
		.options(*message_load_options())
	)
	messages = list(result.scalars().all())
	by_id = {
		str(payload.id): payload for payload in message_payloads(messages, principal)
	}
	for thread, payload in zip(threads, payloads, strict=True):
		payload.last_message = by_id.get(str(thread.current_message_id))


async def thread_payloads(
	session: AsyncSession,
	threads: Sequence[Thread],
	principal: Principal,
	include_last_message: bool = False,
) -> list[ThreadOut]:
	"""build and project thread payloads for the principal."""
	payloads = await build_thread_payloads(session, threads)
	if include_last_message:
		await attach_last_messages(session, threads, payloads, principal)
	return project_private(principal, ResourceType.THREAD, payloads)


async def rebuild_thread_payload(session: AsyncSession, thread_id: TypeID) -> ThreadOut:
	"""invalidate the cached payload and build a fresh one post-mutation."""
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)
	thread = await load_membership_thread(session, thread_id)
	return await build_thread_payload(session, thread)


async def list_participants(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
) -> list[ThreadParticipantOut]:
	"""list the thread roster (humans + groups from the ACL, plus agents)."""
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.READER
	)
	owner_id = await session.scalar(
		select(Thread.owner_id).where(Thread.id == thread_id)
	)
	return await build_roster(session, thread_id, owner_id or principal.user.id)


# membership write operations (ACL grants/revokes)


async def _existing_acl_subjects(
	session: AsyncSession, thread_id: TypeID, owner_id: str | None
) -> tuple[set[str], set[str]]:
	"""return (user_ids, group_ids) that already have access to the thread.

	the owner is included among the users so re-adding them is a no-op rather
	than a spurious invite.
	"""
	rows = (
		await session.execute(
			select(AccessRule.subject_user_id, AccessRule.subject_group_id).where(
				AccessRule.thread_id == str(thread_id)
			)
		)
	).all()
	users: set[str] = {owner_id} if owner_id else set()
	groups: set[str] = set()
	for user_id, group_id in rows:
		if user_id is not None:
			users.add(str(user_id))
		if group_id is not None:
			groups.add(str(group_id))
	return users, groups


async def add_members(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	user_ids: list[TypeID] | None = None,
	group_ids: list[TypeID] | None = None,
	membership_role: str | None = None,
	origin_session_id: str | None = None,
) -> list[ThreadParticipantOut]:
	"""add member(s) - humans and/or live groups - to a thread (EDITOR).

	members are ACL subjects: known users (friends) are granted EDITOR directly;
	strangers become pending READER invites - this IS the invite verb (the
	invitee responds via ``invites``). groups are shared live (a group access
	rule). adding an existing subject is an idempotent no-op. one THREAD_UPDATED
	fanout for the whole batch; returns the roster entries for the subjects
	actually added.
	"""
	_ = membership_role  # reserved, not yet applied
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.EDITOR
	)
	owner_id = await session.scalar(
		select(Thread.owner_id).where(Thread.id == thread_id)
	)
	existing_users, existing_groups = await _existing_acl_subjects(
		session, thread_id, str(owner_id) if owner_id else None
	)

	wanted_users = [
		uid for uid in dict.fromkeys(user_ids or []) if str(uid) not in existing_users
	]
	wanted_groups = [
		gid for gid in dict.fromkeys(group_ids or []) if str(gid) not in existing_groups
	]

	added: set[str] = set()
	user_grants: dict[TypeID, AccessLevel] = {}
	invite_status_by_user: dict[TypeID, str | None] = {}
	for user_id in wanted_users:
		target = await session.get(User, user_id)
		if target is None or not target.is_active:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="user not found",
			)
		if await is_blocked(principal.user.id, user_id, session):
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="cannot add a blocked user",
			)
		is_friend = await are_friends(principal.user.id, user_id, session)
		user_grants[user_id] = AccessLevel.EDITOR if is_friend else AccessLevel.READER
		invite_status_by_user[user_id] = None if is_friend else INVITE_PENDING
		added.add(str(user_id))
	for group_id in wanted_groups:
		await require_resource_access(
			group_id,
			session,
			principal,
			ResourceType.GROUP,
			required_level=AccessLevel.READER,
		)
		added.add(str(group_id))
	await grant_subject_access_batch_unchecked(
		ResourceType.THREAD,
		thread_id,
		user_grants,
		{group_id: AccessLevel.EDITOR for group_id in wanted_groups},
		session,
		actor_user_id=TypeID(principal.user.id),
	)
	for user_id, invite_status in invite_status_by_user.items():
		await ensure_participant(
			thread_id,
			session,
			user_id=user_id,
			invite_status=invite_status,
		)

	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)
	# membership decides the people/solo scope carried by the vector payload.
	await sync_thread_state_vectors(session, [thread_id])
	roster = await build_roster(session, thread_id, owner_id or principal.user.id)
	return [entry for entry in roster if str(entry.id) in added]


async def remove_member(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	*,
	user_id: TypeID | None = None,
	group_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> None:
	"""remove a member (a human or a group) from a thread by revoking its access.

	exactly one of user_id / group_id must be given. revoking emits access.updated,
	which renders inline ("X removed Y" / "Y left" / "X removed the group Z").
	anyone may remove themselves (READER); removing anyone else needs ADMIN. the
	owner cannot be removed (they hold the thread via owner_id). removing a human
	also clears their now-orphaned per-thread state.
	"""
	if (user_id is None) == (group_id is None):
		raise ValueError("exactly one of user_id or group_id is required")

	if group_id is not None:
		await require_thread_access(
			thread_id, session, principal, required_level=AccessLevel.ADMIN
		)
		await revoke_group_access_unchecked(
			ResourceType.THREAD,
			thread_id,
			group_id,
			session,
			actor_user_id=TypeID(principal.user.id),
		)
		await emit_thread_updated(
			session, thread_id, principal, origin_session_id=origin_session_id
		)
		await sync_thread_state_vectors(session, [thread_id])
		return

	assert user_id is not None
	is_self = user_id == principal.user.id
	required = AccessLevel.READER if is_self else AccessLevel.ADMIN
	await require_thread_access(thread_id, session, principal, required_level=required)
	owner_id = await session.scalar(
		select(Thread.owner_id).where(Thread.id == thread_id)
	)
	if owner_id is not None and str(owner_id) == str(user_id):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="the owner cannot be removed from their own thread",
		)
	# drop access first so the removed user's client reacts to access.updated,
	# then clear their now-orphaned per-thread state.
	await revoke_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		user_id,
		session,
		actor_user_id=TypeID(principal.user.id),
	)
	await clear_participant_state(session, thread_id, user_id)
	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)
	await sync_thread_state_vectors(session, [thread_id])
