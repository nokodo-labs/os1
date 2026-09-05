"""per-user thread state: the caller's own relationship to a thread.

a ``thread_participants`` user row is NOT an access grant - access is the ACL.
it holds one user's private state for a thread they can already reach: read
cursor, mute / pin / archive flags, and a pending-invite marker. this module
owns reading, creating and mutating that state (and the read-receipt /
state-change events), plus unread counts and typing indicators.
"""

from fastapi import HTTPException, status
from sqlalchemy import Integer, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Select

from api.constants import PRIVATE_METADATA_KEY
from api.models.access_rule import AccessLevel
from api.models.event_types import EventType
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.permissions import ActionPermission, ResourceType
from api.schemas.thread import (
	ParticipantStatus,
	ThreadListFilters,
	ThreadSearchFilters,
	participant_state_filters,
)
from api.schemas.thread_participant import ThreadUserState
from api.v1.service.authentication import Principal, load_principal_for_user
from api.v1.service.authorization import (
	list_accessible_user_ids_for_resources,
	require_self_or_permission,
	require_thread_access,
	resource_access_predicate,
)
from api.v1.service.events import fanout_live_payload
from api.v1.service.threads.common import (
	INVITE_PENDING,
	INVITE_STATUS_KEY,
)
from api.v1.service.vectorize import sync_resource_vector_payload
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


async def get_thread_participant(
	session: AsyncSession,
	thread_id: TypeID,
	user_id: TypeID | None = None,
	agent_id: TypeID | None = None,
) -> ThreadParticipant | None:
	"""fetch a single user-state or agent-presence row for a thread, if present."""
	subject = (
		ThreadParticipant.user_id == user_id
		if user_id is not None
		else ThreadParticipant.agent_id == agent_id
	)
	result = await session.execute(
		select(ThreadParticipant).where(
			ThreadParticipant.thread_id == thread_id,
			subject,
		)
	)
	return result.scalars().first()


def _to_user_state(
	thread_id: TypeID, state: ThreadParticipant | None
) -> ThreadUserState:
	"""project a user's state row (or its absence) to the API schema."""
	invite_status: str | None = None
	last_read: TypeID | None = None
	muted = pinned = archived = False
	if state is not None:
		raw = (state.metadata_ or {}).get(INVITE_STATUS_KEY)
		invite_status = raw if isinstance(raw, str) else None
		last_read = (
			TypeID(state.last_read_message_id) if state.last_read_message_id else None
		)
		muted, pinned, archived = state.muted, state.pinned, state.archived
	return ThreadUserState(
		thread_id=TypeID(thread_id),
		invite_status=invite_status,
		last_read_message_id=last_read,
		muted=muted,
		pinned=pinned,
		archived=archived,
	)


async def ensure_participant(
	thread_id: TypeID,
	session: AsyncSession,
	user_id: TypeID | None = None,
	agent_id: TypeID | None = None,
	invite_status: str | None = None,
) -> ThreadParticipant:
	"""get or create a state/presence row for a user or agent in a thread.

	exactly one of user_id / agent_id must be set. this row is NOT an access
	grant: a user row only holds that user's per-thread state (read cursor,
	mute/pin/archive, and the pending invite_status); an agent row records the
	agent's presence. access is managed separately via AccessRule.
	"""
	if (user_id is None) == (agent_id is None):
		raise ValueError("exactly one of user_id or agent_id is required")

	participant = await get_thread_participant(
		session, thread_id, user_id=user_id, agent_id=agent_id
	)

	if participant is None:
		participant = ThreadParticipant(
			thread_id=thread_id,
			user_id=user_id,
			agent_id=agent_id,
		)
		if invite_status is not None:
			participant.set_metadata(public={INVITE_STATUS_KEY: invite_status})
		session.add(participant)
		await session.flush()
	elif invite_status is not None:
		metadata = participant.public_metadata
		metadata[INVITE_STATUS_KEY] = invite_status
		participant.set_metadata(public=metadata)
		await session.flush()

	return participant


async def require_user_participant(
	thread_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
) -> ThreadParticipant:
	"""return an existing user participant row or raise a masked 404."""
	participant = await get_thread_participant(session, thread_id, user_id=user_id)
	if participant is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread participant not found",
		)
	return participant


def clear_invite_status(participant: ThreadParticipant) -> None:
	"""drop the pending-invite marker from a user's state row, if present."""
	metadata = participant.public_metadata
	if metadata.pop(INVITE_STATUS_KEY, None) is not None:
		participant.set_metadata(public=metadata)


async def clear_participant_state(
	session: AsyncSession, thread_id: TypeID, user_id: TypeID
) -> None:
	"""delete a user's state row for a thread (on leave / removal / decline).

	state is meaningless once the user no longer has access, so membership ops
	call this after revoking the ACL rule to leave no orphan rows behind.
	"""
	participant = await get_thread_participant(session, thread_id, user_id=user_id)
	if participant is not None:
		await session.delete(participant)


async def _fanout_participant_state(
	session: AsyncSession,
	thread_id: TypeID,
	user_id: TypeID,
	created: bool,
	fields: JSONObject,
	shared: bool,
) -> None:
	"""fan out a participant-state change as thread.participants.added/updated.

	the row's first appearance is ``added``; later changes are ``updated``. the
	event carries no message_id anchor, so it never renders inline. ``shared``
	read-cursor updates go to every thread reader (read receipts); private
	mute/pin/archive updates go only to the subject user's own sessions.
	"""
	event_type = (
		EventType.THREAD_PARTICIPANT_ADDED
		if created
		else EventType.THREAD_PARTICIPANT_UPDATED
	)
	payload = {
		"type": event_type.value,
		"data": {
			"thread_id": str(thread_id),
			"user_id": str(user_id),
			"kind": "user",
			**fields,
		},
	}
	if shared:
		recipients = await list_accessible_user_ids_for_resources(
			[(ResourceType.THREAD, thread_id)], session
		)
		await fanout_live_payload(payload, recipients, None, False)
	else:
		await fanout_live_payload(payload, None, user_id, False)


async def mark_thread_read(
	thread_id: TypeID,
	user_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> ThreadUserState:
	"""mark all messages in a thread as read for the subject user.

	the read cursor is part of the user's participant state, so this updates the
	state row and fans out a shared thread.participants.added/updated event (a
	read receipt) to every thread reader. it carries no message_id, so it never
	renders inline.
	"""
	_ = origin_session_id
	require_state_subject_access(user_id, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)

	existing = await get_thread_participant(session, thread_id, user_id=user_id)
	created = existing is None
	participant = await ensure_participant(thread_id, session, user_id=user_id)

	latest_id = await session.scalar(
		select(Message.id)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at.desc())
		.limit(1)
	)
	if latest_id:
		participant.last_read_message_id = latest_id
	await session.commit()

	await _fanout_participant_state(
		session,
		thread_id,
		user_id,
		created,
		{"last_read_message_id": str(latest_id) if latest_id else None},
		shared=True,
	)
	return _to_user_state(thread_id, participant)


async def update_thread_participant(
	session: AsyncSession,
	principal: Principal,
	thread_id: TypeID,
	user_id: TypeID,
	muted: bool | None = None,
	pinned: bool | None = None,
	archived: bool | None = None,
) -> ThreadUserState:
	"""update the subject user's participant state (mute / pin / archive).

	these flags are personal to the user (unlike read receipts, which are shared
	with co-participants), so the change is fanned out only to the subject's own
	sessions as a thread.participants.added/updated state event - never persisted
	as a shared activity event and never rendered inline.
	"""
	require_state_subject_access(user_id, principal)
	await require_thread_access(
		thread_id, session, principal, required_level=AccessLevel.READER
	)
	participant = await require_user_participant(thread_id, user_id, session)
	if muted is not None:
		participant.muted = muted
	if pinned is not None:
		participant.pinned = pinned
	if archived is not None:
		participant.archived = archived
	await session.commit()

	# keep the searchable state payload in step with the row.
	await sync_thread_state_vectors(session, [thread_id])
	await _fanout_participant_state(
		session,
		thread_id,
		user_id,
		False,
		{
			"muted": participant.muted,
			"pinned": participant.pinned,
			"archived": participant.archived,
		},
		shared=False,
	)
	return _to_user_state(thread_id, participant)


async def get_unread_counts(
	session: AsyncSession,
	principal: Principal,
	user_id: TypeID,
	thread_ids: list[TypeID] | None = None,
) -> dict[TypeID, int]:
	"""return unread message counts per thread for an explicit user.

	counts are computed against that user's own access and read cursors, so an
	operator sees what the user sees. for threads with no state row (or none
	with a read cursor), all messages are unread. see
	``require_state_subject_access`` for the gate.
	"""
	require_state_subject_access(user_id, principal)
	subject = (
		principal
		if str(user_id) == str(principal.user.id)
		else await load_principal_for_user(user_id, session)
	)

	accessible_q = (
		select(Thread.id)
		.where(
			resource_access_predicate(
				subject,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			)
		)
		.where(Thread.is_temporary.is_(False))
	)
	if thread_ids:
		accessible_q = accessible_q.where(Thread.id.in_(thread_ids))
	accessible_subq = accessible_q.scalar_subquery()

	last_read_ts = (
		select(Message.created_at)
		.where(Message.id == ThreadParticipant.last_read_message_id)
		.correlate(ThreadParticipant)
		.scalar_subquery()
	)
	part_alias = (
		select(
			ThreadParticipant.thread_id,
			last_read_ts.label("read_at"),
		)
		.where(ThreadParticipant.user_id == user_id)
		.subquery("part")
	)

	stmt = (
		select(
			Message.thread_id,
			func.count(Message.id).label("cnt"),
		)
		.where(Message.thread_id.in_(accessible_subq))
		.outerjoin(part_alias, Message.thread_id == part_alias.c.thread_id)
		.where(
			or_(
				Message.sender_user_id.is_(None),
				Message.sender_user_id != str(user_id),
			),
			or_(
				part_alias.c.read_at.is_(None),
				Message.created_at > part_alias.c.read_at,
			),
		)
		.group_by(Message.thread_id)
	)

	result = await session.execute(stmt)
	return {TypeID(row.thread_id): row.cnt for row in result if row.cnt > 0}


async def handle_typing_event(
	session: AsyncSession,
	user_id: TypeID,
	thread_id: TypeID,
	typing: bool,
) -> None:
	"""broadcast a typing indicator to all users with access to a thread.

	ephemeral: no event persistence, just fan-out over WS. the sender must be
	among the accessible users; if not, the event is silently dropped.
	"""
	if await get_thread_participant(session, thread_id, user_id=user_id) is None:
		return
	recipient_ids = await list_accessible_user_ids_for_resources(
		[(ResourceType.THREAD, thread_id)], session
	)
	if not recipient_ids or user_id not in recipient_ids:
		return

	msg_type = "typing.start" if typing else "typing.stop"
	payload = {
		"type": msg_type,
		"data": {
			"thread_id": thread_id,
			"user_id": user_id,
		},
	}
	await fanout_live_payload(
		payload,
		recipient_ids,
		None,
		False,
		exclude_user_id=user_id,
	)


# per-user thread-state filtering


_STATUS_COLUMNS = {
	"archived": ThreadParticipant.archived,
	"pinned": ThreadParticipant.pinned,
	"muted": ThreadParticipant.muted,
}


def participant_status_subquery(user_id: TypeID, status: ParticipantStatus) -> Select:
	"""threads where the user's state row has ``status`` set.

	``invite_pending`` reads the json marker; the rest are boolean columns.
	"""
	stmt = select(ThreadParticipant.thread_id).where(
		ThreadParticipant.user_id == user_id
	)
	if status == "invite_pending":
		return stmt.where(
			ThreadParticipant.metadata_[INVITE_STATUS_KEY].as_string() == INVITE_PENDING
		)
	return stmt.where(_STATUS_COLUMNS[status].is_(True))


# vector payload sync: per-user state as filterable keyword arrays
STATE_VECTOR_FIELDS = ("archived_by", "muted_by", "pinned_by", "invite_pending_to")

STATE_VECTORS_SCHEMA_KEY = "state_vectors_schema"
STATE_VECTORS_SCHEMA = 1
"""bump when the state payload field layout changes; the maintenance sweep
repatches every thread whose stamp is missing or older."""


async def thread_state_vector_metadata(
	session: AsyncSession,
	thread_ids: list[TypeID] | list[str],
) -> dict[str, dict[str, list[str]]]:
	"""build the per-user state payload fields for the vectorstore.

	each field lists the users for whom the flag is set, so search can filter
	natively per viewer (see ``STATE_VECTOR_FIELDS``).
	"""
	ids = [str(tid) for tid in thread_ids]
	result: dict[str, dict[str, list[str]]] = {
		tid: {field: [] for field in STATE_VECTOR_FIELDS} for tid in ids
	}
	if not ids:
		return result
	rows = (
		await session.execute(
			select(
				ThreadParticipant.thread_id,
				ThreadParticipant.user_id,
				ThreadParticipant.archived,
				ThreadParticipant.muted,
				ThreadParticipant.pinned,
				ThreadParticipant.metadata_,
			).where(
				ThreadParticipant.thread_id.in_(ids),
				ThreadParticipant.user_id.is_not(None),
			)
		)
	).all()
	for thread_id, user_id, archived, muted, pinned, metadata in rows:
		entry = result.setdefault(
			str(thread_id), {field: [] for field in STATE_VECTOR_FIELDS}
		)
		uid = str(user_id)
		flags = (
			("archived_by", bool(archived)),
			("muted_by", bool(muted)),
			("pinned_by", bool(pinned)),
			(
				"invite_pending_to",
				(metadata or {}).get(INVITE_STATUS_KEY) == INVITE_PENDING,
			),
		)
		for field, is_set in flags:
			if is_set:
				entry.setdefault(field, []).append(uid)
	return result


async def sync_thread_state_vectors(
	session: AsyncSession,
	thread_ids: list[TypeID] | list[str],
) -> None:
	"""push the threads' current state + scope into their vector payloads.

	one state query, parallel payload patches, no re-embedding. stamps
	``STATE_VECTORS_SCHEMA_KEY`` so the maintenance sweep can find threads
	whose payloads predate the current field layout.
	"""
	ids = [str(tid) for tid in thread_ids]
	if not ids:
		return
	metadata = await thread_state_vector_metadata(session, ids)
	await sync_resource_vector_payload(ids, ResourceType.THREAD, metadata, session)
	await session.execute(
		update(Thread)
		.where(Thread.id.in_(ids))
		.values(
			metadata_=Thread.merge_private_metadata_sql(
				{STATE_VECTORS_SCHEMA_KEY: STATE_VECTORS_SCHEMA}
			)
		)
	)
	await session.commit()


def state_vectors_due_predicate() -> ColumnElement[bool]:
	"""SQL predicate matching threads whose state payload layout is stale."""
	schema_text = Thread.metadata_[
		(PRIVATE_METADATA_KEY, STATE_VECTORS_SCHEMA_KEY)
	].as_string()
	return or_(
		schema_text.is_(None),
		cast(schema_text, Integer) != STATE_VECTORS_SCHEMA,
	)


def require_state_subject_access(user_id: TypeID, principal: Principal) -> None:
	"""gate access to a named user's private per-thread state.

	participant state has no access rules of its own, so reaching another
	user's state is a cross-user action and nothing else: users:manage is the
	whole gate. archive / mute / pin / pending-invite are personal state, so
	this is deliberately stricter than users:read. no thread operator
	permission applies - none of this state is operator-only data.
	"""
	require_self_or_permission(user_id, principal, ActionPermission.USERS_MANAGE)


def apply_participant_state_filters(
	stmt: Select,
	filters: ThreadListFilters | ThreadSearchFilters,
	principal: Principal,
) -> Select:
	"""filter a thread listing by named users' per-thread state.

	every state is addressed by an explicit user id (``archived_by`` /
	``not_archived_by`` and friends), so the result never depends on who is
	asking - the principal only gates ACCESS. each named subject is gated,
	since presence or absence in the result discloses their state.
	"""
	for status, include_id, exclude_id in participant_state_filters(filters):
		for user_id in (include_id, exclude_id):
			if user_id is not None:
				require_state_subject_access(user_id, principal)
		if include_id is not None:
			stmt = stmt.where(
				Thread.id.in_(participant_status_subquery(include_id, status))
			)
		if exclude_id is not None:
			stmt = stmt.where(
				Thread.id.not_in(participant_status_subquery(exclude_id, status))
			)
	return stmt
