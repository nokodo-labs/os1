"""thread creation: the single path that produces threads of every shape.

one payload yields a solo AI chat (no members), a 1:1 DM (one member, reused
if an active DM already exists), or a group (several members and/or live
groups), optionally with agents and a per-thread auto-reply agent. also owns
DM de-duplication (an ACL-shape query plus the pair lock that makes
find-or-create atomic) and the message-request notification for strangers.
"""

import hashlib

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel, AccessRule
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ActionPermission, ResourceType
from api.schemas.notification import NotificationPayload
from api.schemas.thread import ThreadCreate
from api.v1.service.access_rules import (
	grant_subject_access_batch_unchecked,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	public_payload,
	require_permission,
	require_resource_access,
)
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.notifications import create_notifications
from api.v1.service.projects import load_projects
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.social.friendship import accepted_friend_ids, blocked_user_ids
from api.v1.service.threads.common import (
	INVITE_PENDING,
	load_thread_payload_source,
)
from api.v1.service.threads.members import build_thread_payload
from api.v1.service.threads.user_state import ensure_participant
from nokodo_ai.utils.typeid import TypeID


async def _invalidate_project_payload_caches(project_ids: set[TypeID]) -> None:
	for project_id in project_ids:
		await invalidate_resource_payload_cache(ResourceType.PROJECT, project_id)


async def create_thread(
	thread_in: ThreadCreate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
	override_id: TypeID | None = None,
) -> Thread:
	"""create a thread of any shape from a single payload.

	members are friend-gated: non-friends are added as pending invites instead
	of being granted access immediately (see ``members.add_members``, which is
	the same gate applied after creation).
	"""
	require_permission(principal, ActionPermission.THREADS_CREATE)
	owner_id = thread_in.owner_id
	if not principal.user.is_superuser:
		owner_id = TypeID(principal.user.id)
	else:
		owner = await session.get(User, owner_id)
		if not owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)

	# resolve the humans, agents, and groups requested at creation
	member_ids = [
		uid for uid in dict.fromkeys(thread_in.member_user_ids) if uid != owner_id
	]
	agent_ids = list(dict.fromkeys(thread_in.agent_ids))
	group_ids = list(dict.fromkeys(thread_in.group_ids))

	if member_ids:
		blocked = await blocked_user_ids(owner_id, member_ids, session)
		if blocked:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="cannot message a blocked user",
			)
	for agent_id in agent_ids:
		await require_resource_access(
			agent_id,
			session,
			principal,
			ResourceType.AGENT,
			required_level=AccessLevel.READER,
		)
	for group_id in group_ids:
		await require_resource_access(
			group_id,
			session,
			principal,
			ResourceType.GROUP,
			required_level=AccessLevel.READER,
		)
	# reuse an existing 1:1 DM rather than spawning duplicates. the pair lock
	# makes find-or-create atomic across processes: without it, two concurrent
	# FIRST-time creations both find nothing (no row exists to row-lock yet)
	# and both create. the second creator blocks here until the first commits,
	# then finds and reuses the committed DM.
	if len(member_ids) == 1 and not agent_ids and not group_ids:
		await _acquire_dm_pair_lock(session, owner_id, member_ids[0])
		existing = await _find_dm_thread(session, owner_id, member_ids[0])
		if existing is not None:
			return await load_thread_payload_source(existing, session)

	projects = await load_projects(
		thread_in.project_ids, session, principal, required_level=AccessLevel.EDITOR
	)
	thread_data = thread_in.model_dump(
		exclude={
			"project_ids",
			"member_user_ids",
			"agent_ids",
			"group_ids",
			"metadata",
		},
	)
	thread_data["owner_id"] = owner_id
	if override_id is not None:
		thread_data["id"] = override_id
	thread = Thread(**thread_data)
	thread.set_metadata(public=dict(thread_in.metadata))
	thread.projects = projects
	session.add(thread)
	await session.flush()

	# owner is implicitly admin via thread.owner_id - no access rule needed; a
	# state row is created so the owner has a read cursor from the start.
	await ensure_participant(thread.id, session, user_id=owner_id)
	for agent_id in agent_ids:
		await ensure_participant(thread.id, session, agent_id=agent_id)
	friends = await accepted_friend_ids(owner_id, member_ids, session)
	user_grants = {
		user_id: (AccessLevel.EDITOR if user_id in friends else AccessLevel.READER)
		for user_id in member_ids
	}
	await grant_subject_access_batch_unchecked(
		ResourceType.THREAD,
		thread.id,
		user_grants,
		{group_id: AccessLevel.EDITOR for group_id in group_ids},
		session,
		actor_user_id=owner_id,
	)
	pending_ids: list[TypeID] = []
	for user_id in member_ids:
		is_friend = user_id in friends
		# known person -> editor (access.updated renders "added"); stranger ->
		# pending reader invite (renders "invited") until they respond.
		await ensure_participant(
			thread.id,
			session,
			user_id=user_id,
			invite_status=None if is_friend else INVITE_PENDING,
		)
		if not is_friend:
			pending_ids.append(user_id)

	# reload with participants so the payload + event carry the full roster
	thread = await load_thread_payload_source(
		thread.id,
		session,
		include_hidden=thread.is_temporary,
	)

	event = Event(
		scope=EventScope.THREAD,
		scope_id=thread.id,
		type=EventType.THREAD_CREATED,
		data=public_payload(await build_thread_payload(session, thread)).model_dump(
			mode="json"
		),
		user_id=str(owner_id),
		thread_id=thread.id,
	)
	await persist_and_fanout_event(
		session, event=event, origin_session_id=origin_session_id
	)
	for user_id in pending_ids:
		await _notify_message_request(session, principal, user_id, thread.id)
	await _invalidate_project_payload_caches({project.id for project in projects})

	return thread


# DM de-duplication


def _dm_pair_lock_key(a: TypeID, b: TypeID) -> int:
	"""stable signed-64 advisory lock key for an unordered user pair."""
	pair = ":".join(sorted((str(a), str(b))))
	digest = hashlib.sha256(pair.encode()).digest()
	return int.from_bytes(digest[:8], "big", signed=True)


async def _acquire_dm_pair_lock(session: AsyncSession, a: TypeID, b: TypeID) -> None:
	"""serialize DM find-or-create for a user pair (transaction-scoped).

	pg_advisory_xact_lock releases automatically at commit/rollback; postgres
	is the lock authority because app locks cannot span worker processes.
	"""
	await session.execute(select(func.pg_advisory_xact_lock(_dm_pair_lock_key(a, b))))


async def _find_dm_thread(
	session: AsyncSession,
	me_id: TypeID,
	target_user_id: TypeID,
) -> TypeID | None:
	"""find an existing DM owned by me and shared with exactly the target.

	a pure DM is mine (owner), shares with exactly one other human (a single
	user access rule, for the target), has no group access rules, and has no
	agent participant rows. membership is the ACL, so this is expressed over
	access rules, not a roster table.
	"""
	# the lone non-owner human is a single user access rule for the other party.
	target_rule = select(AccessRule.thread_id).where(
		AccessRule.thread_id.is_not(None),
		AccessRule.subject_user_id == target_user_id,
	)
	me_rule = select(AccessRule.thread_id).where(
		AccessRule.thread_id.is_not(None),
		AccessRule.subject_user_id == me_id,
	)
	# more than one user-subject rule, or any group rule, disqualifies a DM.
	multi_human = (
		select(AccessRule.thread_id)
		.where(
			AccessRule.thread_id.is_not(None),
			AccessRule.subject_user_id.is_not(None),
		)
		.group_by(AccessRule.thread_id)
		.having(func.count(func.distinct(AccessRule.subject_user_id)) > 1)
	)
	has_group = select(AccessRule.thread_id).where(
		AccessRule.thread_id.is_not(None),
		AccessRule.subject_group_id.is_not(None),
	)
	has_agent = select(ThreadParticipant.thread_id).where(
		ThreadParticipant.agent_id.is_not(None),
	)
	stmt = (
		select(Thread.id)
		.where(
			Thread.is_temporary.is_(False),
			Thread.deleted_at.is_(None),
			# either i own it and shared with the target, or vice versa.
			or_(
				and_(
					Thread.owner_id == me_id,
					Thread.id.in_(target_rule),
				),
				and_(
					Thread.owner_id == target_user_id,
					Thread.id.in_(me_rule),
				),
			),
			Thread.id.not_in(multi_human),
			Thread.id.not_in(has_group),
			Thread.id.not_in(has_agent),
		)
		.order_by(Thread.last_activity_at.desc())
		.limit(1)
		.with_for_update()
	)
	row = (await session.execute(stmt)).scalar_one_or_none()
	return TypeID(row) if row is not None else None


async def _notify_message_request(
	session: AsyncSession,
	principal: Principal,
	target_user_id: TypeID,
	thread_id: TypeID,
) -> None:
	"""send a durable "wants to message you" notification to a non-friend."""
	sender_name = principal.subject.display_name or principal.subject.username
	payload = NotificationPayload(
		title="new message request",
		body=f"{sender_name} wants to message you",
		tag=f"invite:{thread_id}",
		action_url="/messages",
		data={"thread_id": str(thread_id), "kind": "message_request"},
	)
	await create_notifications(session, payload, [target_user_id])
