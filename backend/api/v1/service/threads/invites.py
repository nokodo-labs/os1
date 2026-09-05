"""thread message-request (invite) flow: the INVITEE side only.

there is no separate "invite" verb - inviting IS ``members.add_members``:
membership grants are friend-gated, so adding a non-friend grants READER plus
a pending-invite marker on their state row (renders "invited"). this module is
the invitee acting on themselves: accept (READER -> EDITOR), decline (drop
access + state), or block the initiator. accept/decline mutate the ACL via
``access_rules`` and the state via ``user_state``; the durable acl.* events
render the join/leave inline. LISTING pending invites is not here: it is the
``invite_pending_for=<user_id>`` filter on the thread listing.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.post_commit import run_post_commit_actions_safely
from api.models.access_rule import AccessLevel
from api.models.block import Block
from api.permissions import ResourceType
from api.schemas.thread import Thread as ThreadOut
from api.v1.service.access_rules import (
	grant_user_access_unchecked,
	revoke_user_access_unchecked,
)
from api.v1.service.authentication import Principal
from api.v1.service.authorization import project_private
from api.v1.service.social.friendship import is_blocked
from api.v1.service.threads.common import (
	INVITE_PENDING,
	INVITE_STATUS_KEY,
	emit_thread_updated,
	load_membership_thread,
)
from api.v1.service.threads.members import rebuild_thread_payload
from api.v1.service.threads.user_state import (
	clear_invite_status,
	clear_participant_state,
	get_thread_participant,
	require_state_subject_access,
	sync_thread_state_vectors,
)
from nokodo_ai.utils.typeid import TypeID


async def accept_invite(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	user_id: TypeID,
	origin_session_id: str | None = None,
) -> ThreadOut:
	"""accept a pending message request, joining the thread."""
	require_state_subject_access(user_id, principal)
	participant = await get_thread_participant(session, thread_id, user_id=user_id)
	# a state row alone is not an invite: rows also appear from read cursors or
	# mute/pin on plain shares. only the pending marker authorizes the editor
	# upgrade, otherwise a read-only share could self-escalate via accept.
	if (
		participant is None
		or (participant.metadata_ or {}).get(INVITE_STATUS_KEY) != INVITE_PENDING
	):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="invite not found",
		)
	clear_invite_status(participant)
	await session.flush()
	# accepting upgrades the read-only invite to full editor access in place;
	# the reader->editor upsert emits access.updated (actor == subject), which
	# renders as "joined".
	await grant_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		user_id,
		session,
		level=AccessLevel.EDITOR,
		actor_user_id=principal.user.id,
	)
	await emit_thread_updated(
		session, thread_id, principal, origin_session_id=origin_session_id
	)
	# the pending marker is searchable state; keep the payload in step.
	await sync_thread_state_vectors(session, [thread_id])
	return project_private(
		principal,
		ResourceType.THREAD,
		[await rebuild_thread_payload(session, thread_id)],
	)[0]


async def decline_invite(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	user_id: TypeID,
	origin_session_id: str | None = None,
) -> None:
	"""decline a pending message request and drop access to the thread."""
	_ = origin_session_id
	require_state_subject_access(user_id, principal)
	participant = await get_thread_participant(session, thread_id, user_id=user_id)
	if participant is None:
		return
	await revoke_user_access_unchecked(
		ResourceType.THREAD,
		thread_id,
		user_id,
		session,
		actor_user_id=principal.user.id,
	)
	# declining hard-deletes the pending state row - it never became membership.
	await clear_participant_state(session, thread_id, user_id)
	await session.commit()
	await run_post_commit_actions_safely(session)
	await sync_thread_state_vectors(session, [thread_id])


async def block_invite(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	user_id: TypeID,
	origin_session_id: str | None = None,
) -> None:
	"""block the thread initiator, then decline the request."""
	require_state_subject_access(user_id, principal)
	thread = await load_membership_thread(session, thread_id)
	initiator_id = thread.owner_id
	if initiator_id != user_id and not await is_blocked(user_id, initiator_id, session):
		session.add(Block(blocker_id=user_id, blocked_id=initiator_id))
		await session.flush()
	await decline_invite(session, principal, thread_id, user_id, origin_session_id)
