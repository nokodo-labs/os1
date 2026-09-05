"""shared, dependency-free primitives for the thread service modules.

this is the bottom of the threads package: event-emit + thread-load helpers, the
shared thread-metadata keys, and the pure ACL thread-scope/filter queries that
both the listing path (``core``) and the per-user-state path (``user_state``)
compose. nothing here imports the higher modules, so there are no cycles.
"""

from collections.abc import Sequence
from typing import overload

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.sql import ColumnElement
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.selectable import Select

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message
from api.models.project import Project
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.permissions import ResourceType
from api.schemas.message import Message as MessageOut
from api.schemas.message import MessageCreatedFrame, MessageSplice
from api.schemas.thread import ParticipantScope, ThreadListFilters
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	apply_resource_access_list_filters,
	project_private,
	public_payload,
	resource_access_predicate,
	resource_derived_access_predicate,
)
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.search import contains_pattern
from nokodo_ai.utils.typeid import TypeID


# shared thread-metadata + participant-state keys.
INVITE_STATUS_KEY = "invite_status"
INVITE_PENDING = "pending"

# sortable thread columns shared by every thread-listing query.
_THREAD_SORT_COLUMNS = {
	"last_activity_at": Thread.last_activity_at,
	"created_at": Thread.created_at,
	"updated_at": Thread.updated_at,
	"title": Thread.title,
}


def participant_load_options() -> list[ExecutableOption]:
	"""eager-load the agent-presence rows used when building a thread roster."""
	return [selectinload(Thread.participants).selectinload(ThreadParticipant.agent)]


def message_load_options() -> list[ExecutableOption]:
	"""eager-load the link rows ``Message.attachments`` and ``.mentions`` read.

	both are properties over relationships, so a payload built without these
	lazy-loads mid-serialization.
	"""
	return [
		selectinload(Message.attachment_links),
		selectinload(Message.mention_links),
	]


def message_payloads(messages: list[Message], principal: Principal) -> list[MessageOut]:
	"""project message rows to their API payloads for the principal."""
	return project_private(
		principal,
		ResourceType.MESSAGE,
		[MessageOut.from_row(message) for message in messages],
	)


def message_event_data(message: Message) -> dict[str, object]:
	"""serialize a message row as a message event payload.

	events fan out to every thread subscriber, so this is the public view.
	"""
	return public_payload(MessageOut.from_row(message)).model_dump(
		mode="json", by_alias=True
	)


def message_created_frame_data(
	message: Message,
	splice: MessageSplice,
) -> dict[str, object]:
	"""serialize a message row and its applied splice as an SSE frame payload.

	the stream twin of ``message_event_data``: same public view, plus where the
	message landed, which only the writer knows.
	"""
	base = MessageOut.model_validate(message)
	frame = MessageCreatedFrame.model_construct(**dict(base), splice=splice)
	return frame.model_dump(mode="json", by_alias=True)


def ensure_admin_for_hidden_or_deleted(
	include_hidden: bool,
	include_deleted: bool,
	principal: Principal,
) -> None:
	"""only superusers may widen a query to hidden or deleted threads."""
	if (include_hidden or include_deleted) and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


@overload
async def load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Thread: ...


@overload
async def load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: None = None,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Thread: ...


async def load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal | None = None,
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Thread:
	"""load one thread with projects + participants, enforcing access.

	passing ``principal=None`` skips the access predicate: only for internal
	callers that have already authorized (or intentionally bypass) access.
	"""
	options = [
		selectinload(Thread.projects),
		*participant_load_options(),
	]
	stmt = select(Thread).options(*options).where(Thread.id == thread_id)
	if not include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))
	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)

	if principal is not None:
		ensure_admin_for_hidden_or_deleted(
			include_hidden,
			include_deleted,
			principal,
		)
		stmt = stmt.where(
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=required_level,
				include_link_access=True,
			)
		)
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def load_thread_payload_source(
	thread_id: TypeID,
	session: AsyncSession,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Thread:
	"""load a thread for payload building, without any access check."""
	stmt = (
		select(Thread)
		.options(selectinload(Thread.projects), *participant_load_options())
		.where(Thread.id == thread_id)
	)
	if include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	if not include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()
	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)
	return thread


async def multi_writer_thread_ids(
	session: AsyncSession,
	thread_ids: Sequence[str | TypeID],
) -> set[str]:
	"""which of the given threads have two or more writers.

	the batched form of ``is_multi_writer_thread``, for callers that resolve
	visibility across a page of threads at once.
	"""
	ids = [str(tid) for tid in thread_ids]
	if not ids:
		return set()
	rows = await session.scalars(
		select(Thread.id).where(
			Thread.id.in_(ids),
			multi_writer_thread_condition(),
		)
	)
	return {str(thread_id) for thread_id in rows}


async def load_membership_thread(session: AsyncSession, thread_id: TypeID) -> Thread:
	"""load an active thread with agent-presence + projects for payload building."""
	stmt = (
		select(Thread)
		.where(
			Thread.id == thread_id,
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		.options(selectinload(Thread.projects), *participant_load_options())
	)
	thread = (await session.execute(stmt)).scalars().unique().one_or_none()
	if thread is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread not found",
		)
	return thread


async def thread_head_id(session: AsyncSession, thread_id: TypeID) -> TypeID | None:
	"""return the thread's current head message id, to anchor an activity event."""
	return await session.scalar(
		select(Thread.current_message_id).where(Thread.id == thread_id)
	)


async def emit_thread_updated(
	session: AsyncSession,
	thread_id: TypeID,
	principal: Principal,
	data: JSONObject | None = None,
	origin_session_id: str | None = None,
) -> None:
	"""fan out a THREAD_UPDATED event and drop the cached thread payload."""
	payload: JSONObject = {"id": str(thread_id)}
	if data:
		payload.update(data)
	await persist_and_fanout_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data=payload,
			user_id=principal.user.id,
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)


# --- shared thread-scope / listing query scaffolding ---


def multi_writer_thread_condition() -> ColumnElement[bool]:
	"""whether the correlated thread row is a people conversation.

	people vs solo IS the writer count: readers are spectators, so a chat
	shared read-only stays solo, and a group share counts through the group's
	members rather than as one extra head. usable in any statement that
	selects from ``threads``.

	the writer set is the SQL twin of ``resolve_resource_access_user_ids(...,
	EDITOR)``: active users who own the thread, are carried to editor or admin
	by the last rule matching them (user, group membership, role, or the
	everyone rule), reach that level through a role/global default, or inherit
	it from a linked project. operators are excluded - a superuser is not a
	participant - and agents are not users, so they never count.
	"""
	candidate = aliased(User)
	writer_count = (
		select(func.count())
		.select_from(candidate)
		.where(
			candidate.is_active.is_(True),
			resource_derived_access_predicate(
				candidate.id,
				ResourceType.THREAD,
				required_level=AccessLevel.EDITOR,
			),
		)
		.correlate(Thread)
		.scalar_subquery()
	)
	return writer_count > 1


def apply_participant_scope(stmt: Select, scope: ParticipantScope) -> Select:
	"""filter threads by whether they are people conversations or solo chats."""
	if scope == "all":
		return stmt
	condition = multi_writer_thread_condition()
	return stmt.where(condition if scope == "people" else ~condition)


async def is_multi_writer_thread(session: AsyncSession, thread_id: TypeID) -> bool:
	"""whether more than one active user resolves to editor access or higher."""
	return bool(
		await session.scalar(
			select(multi_writer_thread_condition())
			.select_from(Thread)
			.where(Thread.id == thread_id)
		)
	)


def base_thread_list_stmt(principal: Principal) -> Select:
	"""start a thread-listing query gated to threads the principal can read.

	only ``projects`` is eager-loaded: the payload projection reads scalars +
	projects, and rosters are resolved for the whole page in one batched pass
	(``members.build_thread_payloads``). eager-loading participants here would
	pay for the roster twice, and messages are never read by a listing.
	"""
	return (
		select(Thread)
		.options(selectinload(Thread.projects))
		.where(
			resource_access_predicate(
				principal,
				ResourceType.THREAD,
				required_level=AccessLevel.READER,
			)
		)
	)


def apply_thread_filters(
	stmt: Select, filters: ThreadListFilters, principal: Principal
) -> Select:
	"""apply the shared list/count filters (scope, owner, q, temp, hidden).

	this is the user-agnostic portion of thread listing; per-user exclusions
	(pending invites, archived) are layered on by the caller, since they are
	participant-state knowledge owned by ``user_state``.
	"""
	if filters.include_hidden and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	if filters.include_deleted and not principal.user.is_superuser:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	if filters.owner_id is not None:
		stmt = stmt.where(Thread.owner_id == filters.owner_id)
	if filters.project_id is not None:
		stmt = stmt.where(Thread.projects.any(Project.id == str(filters.project_id)))
	if not filters.include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))
	if filters.q is not None and filters.q.strip():
		pattern = contains_pattern(filters.q.strip())
		stmt = stmt.where(Thread.title.ilike(pattern, escape="\\"))
	stmt = apply_resource_access_list_filters(
		stmt,
		principal,
		ResourceType.THREAD,
		filters.access_relationship,
		filters.resolved_access_level,
	)
	stmt = apply_participant_scope(stmt, filters.participant_scope)
	if filters.include_deleted:
		stmt = stmt.execution_options(include_deleted=True)
	return stmt


def apply_thread_sort(stmt: Select, sort_by: str, sort_dir: SortDir) -> Select:
	"""apply the shared thread sort columns + id tie-breaker."""
	return apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns=_THREAD_SORT_COLUMNS,
		tie_breaker=Thread.id,
	)
