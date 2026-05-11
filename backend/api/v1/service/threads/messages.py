"""service helpers for threads and messages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.permissions import ResourceType
from api.schemas.message import MessageCreate, MessageUpdate
from api.schemas.sorting import CommonSortBy
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.threads.core import (
	_ensure_admin_for_hidden,
	_load_thread,
	_message_event_data,
)
from api.v1.service.threads.participants import ensure_participant
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


async def _invalidate_thread_payload(thread_id: TypeID) -> None:
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)


async def list_messages(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 100,
	sort_by: CommonSortBy = "created_at",
	sort_dir: SortDir = "desc",
	group_task_runs: bool = True,
	include_hidden: bool = False,
) -> list[Message]:
	_ensure_admin_for_hidden(include_hidden, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)
	base_stmt = select(Message).where(Message.thread_id == thread_id)
	base_stmt = apply_sort(
		base_stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"created_at": Message.created_at,
			"updated_at": Message.updated_at,
		},
		tie_breaker=Message.id,
	)
	page_result = await session.execute(base_stmt.offset(skip).limit(limit))
	items = list(page_result.scalars().all())
	if not group_task_runs or not items:
		return items

	# identify consecutive tool messages at the "latest" edge of this page.
	tool_block: list[Message] = []
	edge = items if sort_dir == "desc" else reversed(items)
	for msg in edge:
		if msg.type != MessageType.TOOL:
			break
		tool_block.append(msg)

	if not tool_block:
		return items

	tool_call_ids = {
		tid for m in tool_block if isinstance(tid := m.tool_call_id, str) and tid != ""
	}
	if not tool_call_ids:
		return items

	def _has_all_tool_calls(msg: Message) -> bool:
		if msg.type != MessageType.ASSISTANT:
			return False
		seen = {tc.get("id") for tc in msg.tool_calls or []}
		return tool_call_ids.issubset(seen)

	# check if parent assistant message is already in page
	adj_index = (
		len(tool_block) if sort_dir == "desc" else len(items) - len(tool_block) - 1
	)
	if 0 <= adj_index < len(items) and _has_all_tool_calls(items[adj_index]):
		return items

	# fetch the nearest preceding assistant message that includes all tool call ids.
	anchor = min(tool_block, key=lambda m: (m.created_at, m.id))
	boundary_predicate = (Message.created_at < anchor.created_at) | (
		(Message.created_at == anchor.created_at) & (Message.id < anchor.id)
	)
	assistant_stmt = (
		select(Message)
		.where(
			Message.thread_id == thread_id,
			Message.type == MessageType.ASSISTANT,
			boundary_predicate,
		)
		.order_by(Message.created_at.desc(), Message.id.desc())
		.limit(25)
	)
	if run_id := anchor.metadata_.get("run_id"):
		assistant_stmt = assistant_stmt.where(
			Message.metadata_["run_id"].as_string() == run_id
		)

	assistant_result = await session.execute(assistant_stmt)
	assistant_msg = next(
		(m for m in assistant_result.scalars() if _has_all_tool_calls(m)),
		None,
	)
	if assistant_msg is None:
		return items

	# insert while preserving the requested sort order.
	insert_at = len(tool_block) if sort_dir == "desc" else len(items) - len(tool_block)
	return [*items[:insert_at], assistant_msg, *items[insert_at:]]


async def list_events_for_message_ids(
	thread_id: TypeID,
	message_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	event_types: list[EventType] | None = None,
) -> list[Event]:
	"""return events associated with the given messages in this thread.

	authz is based on thread access (viewer+), not the global events permission.
	when event_types is provided, only events of those types are returned.
	"""
	_ensure_admin_for_hidden(include_hidden, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)

	if not message_ids:
		return []

	conditions = [
		Event.thread_id == str(thread_id),
		Event.message_id.in_([str(mid) for mid in message_ids]),
	]
	if event_types:
		conditions.append(Event.type.in_(event_types))

	stmt = select(Event).where(*conditions).order_by(Event.created_at).limit(2000)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_message_tree(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""return all messages in a thread as a flat list."""
	_ensure_admin_for_hidden(include_hidden, principal)
	return await list_messages(
		thread_id,
		session,
		principal=principal,
		skip=0,
		limit=10_000,
		sort_by="created_at",
		sort_dir="asc",
		group_task_runs=False,
		include_hidden=include_hidden,
	)


async def get_current_branch(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""return the root-leaf path ending at thread.current_message_id."""
	_ensure_admin_for_hidden(include_hidden, principal)
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)
	if not thread.current_message_id:
		return []

	return await walk_message_branch(session, thread.current_message_id)


async def walk_message_branch(
	session: AsyncSession,
	leaf_id: TypeID,
) -> list[Message]:
	"""walk from root to the given leaf without doing access checks."""
	return await _walk_branch_cte(session, leaf_id)


async def _walk_branch_cte(
	session: AsyncSession,
	leaf_id: TypeID,
) -> list[Message]:
	"""walk from leaf to root using a recursive CTE, return root-first order."""
	msg_t = Message.__table__

	anchor = (
		select(
			msg_t.c.id.label("msg_id"),
			msg_t.c.parent_id.label("msg_parent_id"),
			literal(0).label("depth"),
		)
		.where(msg_t.c.id == str(leaf_id))
		.cte(name="branch", recursive=True)
	)

	recursive = select(
		msg_t.c.id.label("msg_id"),
		msg_t.c.parent_id.label("msg_parent_id"),
		(anchor.c.depth + 1).label("depth"),
	).where(msg_t.c.id == anchor.c.msg_parent_id)

	branch_cte = anchor.union_all(recursive)

	stmt = (
		select(Message)
		.join(branch_cte, Message.id == branch_cte.c.msg_id)
		.order_by(branch_cte.c.depth.desc())
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def load_thread_with_branch(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	parent_id: TypeID | None = None,
) -> tuple[Thread, list[Message]]:
	"""load a thread and its message branch in minimal queries.

	optimized for the run path: skips selectinload(projects) since they
	are not needed during agent execution, and uses a recursive CTE for
	branch walking instead of per-message queries.

	returns (thread, branch_messages) where branch is root-first.
	"""
	stmt = select(Thread).where(
		Thread.id == thread_id,
		thread_access_predicate(principal, required_level=AccessLevel.READER),
	)
	result = await session.execute(stmt)
	thread = result.scalars().one_or_none()
	if thread is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="thread not found",
		)

	# determine effective head for branch walk
	head_id = parent_id if parent_id else thread.current_message_id
	if not head_id:
		return thread, []

	branch = await _walk_branch_cte(session, head_id)
	return thread, branch


async def switch_branch(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Thread:
	"""set current_message_id to the deepest leaf descending from message_id."""
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	msg = await session.get(Message, message_id)
	if not msg or msg.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Message not found",
		)

	leaf_id: TypeID = message_id
	while True:
		children_stmt = (
			select(Message)
			.where(Message.thread_id == thread_id, Message.parent_id == leaf_id)
			.order_by(Message.created_at)
		)
		children = list((await session.execute(children_stmt)).scalars().all())
		if not children:
			break
		leaf_id = TypeID(children[-1].id)

	thread.current_message_id = leaf_id

	# emit thread.updated event for branch switch
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.THREAD_UPDATED,
		data={
			"id": str(thread_id),
			"current_message_id": str(leaf_id),
		},
		user_id=principal.user_id,
		thread_id=str(thread_id),
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	try:
		await session.commit()
	except IntegrityError as exc:
		# fk race: leaf_id was deleted by another tx between our select and
		# this commit. surface as 409 instead of 500.
		await session.rollback()
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="branch state changed concurrently; please retry",
		) from exc
	await _invalidate_thread_payload(thread_id)
	return thread


async def create_message(
	thread_id: TypeID,
	message_in: MessageCreate,
	session: AsyncSession,
	principal: Principal,
	message_id: TypeID | None = None,
	origin_session_id: str | None = None,
) -> Message:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	data = message_in.model_dump(by_alias=True, exclude={"type"})
	sender_user_id = data.get("sender_user_id")
	if (
		sender_user_id is not None
		and not principal.is_admin
		and str(sender_user_id) != str(principal.user.id)
	):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	if message_in.type == MessageType.USER and sender_user_id is None:
		data["sender_user_id"] = principal.user.id
	parent_id = data.pop("parent_id", None)
	# only default to current_message_id when the caller did NOT explicitly
	# set parent_id. an explicit null means "create a root message" (e.g.
	# sibling of the first message when editing).
	if parent_id is None and "parent_id" not in message_in.model_fields_set:
		parent_id = thread.current_message_id
	elif parent_id is not None:
		parent = await session.get(Message, parent_id)
		if not parent or parent.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Parent message not found",
			)

	pk: dict[str, object] = {"id": message_id} if message_id is not None else {}

	polymorphic_entry = Message.__mapper__.polymorphic_map.get(message_in.type)
	if polymorphic_entry is None:
		message_cls = Message.__mapper__.polymorphic_map[MessageType.USER].class_
	else:
		message_cls = polymorphic_entry.class_

	message: Message = message_cls(
		thread_id=thread_id,
		parent_id=parent_id,
		**pk,
		**data,
	)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.flush()
	thread.current_message_id = message.id

	# ensure sender is tracked as a participant
	await ensure_participant(thread_id, principal.user.id, session)

	await session.commit()

	await session.refresh(thread, attribute_names=["last_activity_at", "updated_at"])

	# emit message.created event with full message payload
	message_data = _message_event_data(message)
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_CREATED,
			data=message_data,
			user_id=principal.user_id,
			thread_id=str(thread_id),
			message_id=str(message.id),
		),
		origin_session_id=origin_session_id,
	)

	# emit thread.updated so all sessions reorder the sidebar by last_activity_at
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"last_activity_at": thread.last_activity_at.isoformat(),
				"updated_at": thread.updated_at.isoformat(),
			},
			user_id=str(thread.owner_id),
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
	await _invalidate_thread_payload(thread_id)

	return message


async def update_user_message(
	thread_id: TypeID,
	message_id: TypeID,
	message_in: MessageUpdate,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Message:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	message = await session.get(Message, message_id)
	if not message or message.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	if message.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="only user messages can be edited",
		)
	if not principal.is_admin and str(message.sender_user_id) != str(principal.user.id):
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)
	update_data = message_in.model_dump(exclude_unset=True, by_alias=True)
	if "content" in message_in.model_fields_set:
		if isinstance(message_in.content, str):
			update_data["content"] = (
				[{"type": "text", "text": message_in.content}]
				if message_in.content
				else []
			)
		else:
			update_data["content"] = [
				part.model_dump(mode="json") for part in message_in.content
			]
	for field, value in update_data.items():
		setattr(message, field, value)
	now = datetime.now(tz=UTC)
	message.updated_at = now
	thread.last_activity_at = now
	thread.updated_at = now
	await session.flush()
	await session.commit()
	await session.refresh(message)

	message_data = _message_event_data(message)
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_UPDATED,
			data=message_data,
			user_id=principal.user_id,
			thread_id=str(thread_id),
			message_id=str(message.id),
		),
		origin_session_id=origin_session_id,
	)

	# emit thread.updated so all sessions reorder the sidebar
	await session.refresh(thread, attribute_names=["last_activity_at", "updated_at"])
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"last_activity_at": thread.last_activity_at.isoformat(),
				"updated_at": thread.updated_at.isoformat(),
			},
			user_id=str(thread.owner_id),
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
	await _invalidate_thread_payload(thread_id)

	return message


async def _find_deepest_leaf(
	session: AsyncSession,
	thread_id: TypeID,
	start_id: str | None,
	exclude: set[str],
) -> str | None:
	"""walk from start_id down to the deepest remaining leaf, excluding IDs."""
	if start_id is None:
		result = await session.execute(
			select(Message.id)
			.where(
				Message.thread_id == str(thread_id),
				Message.parent_id.is_(None),
				Message.id.notin_(list(exclude)),
			)
			.order_by(Message.created_at)
		)
		roots = [str(row[0]) for row in result]
		if not roots:
			return None
		start_id = roots[-1]

	leaf_id = start_id
	while True:
		result = await session.execute(
			select(Message.id)
			.where(
				Message.parent_id == leaf_id,
				Message.id.notin_(list(exclude)),
			)
			.order_by(Message.created_at)
		)
		children = [str(row[0]) for row in result]
		if not children:
			break
		leaf_id = children[-1]
	return leaf_id


async def delete_user_message_turn(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	"""delete a user message and its entire descendant subtree.

	all children (assistant responses, follow-up messages, tool messages,
	alternate regeneration branches) are recursively deleted.
	"""
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)

	target = await session.get(Message, str(message_id))
	if not target or TypeID(target.thread_id) != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Message not found",
		)
	if target.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="only user messages can be deleted",
		)

	parent_id = target.parent_id

	# collect the entire subtree via BFS (level-by-level for efficiency)
	deleted_ids: list[str] = [str(message_id)]
	frontier: list[str] = [str(message_id)]
	while frontier:
		result = await session.execute(
			select(Message.id).where(Message.parent_id.in_(frontier))
		)
		children = [str(row[0]) for row in result]
		deleted_ids.extend(children)
		frontier = children

	deleted_set = set(deleted_ids)

	# compute new current_message_id before deleting
	if thread.current_message_id and str(thread.current_message_id) in deleted_set:
		leaf = await _find_deepest_leaf(
			session, thread_id, parent_id, exclude=deleted_set
		)
		thread.current_message_id = TypeID(leaf) if leaf else None

	thread.last_activity_at = datetime.now(tz=UTC)

	# capture before publish_event commits (expiring all ORM attributes)
	owner_id = str(thread.owner_id)

	# bulk-delete subtree; DB CASCADE on event FKs handles cleanup
	await session.execute(sa_delete(Message).where(Message.id.in_(deleted_ids)))

	# emit message.deleted event
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.MESSAGE_DELETED,
			data={
				"thread_id": str(thread_id),
				"message_id": str(message_id),
				"parent_id": parent_id,
				"deleted_ids": deleted_ids,
			},
			user_id=principal.user_id,
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
	await _invalidate_thread_payload(thread_id)

	# publish_event commits; refresh thread to get server-side updated_at
	await session.refresh(thread, attribute_names=["last_activity_at", "updated_at"])

	# emit thread.updated so all sessions reorder the sidebar
	await event_service.publish_event(
		session,
		event=Event(
			scope=EventScope.THREAD,
			scope_id=str(thread_id),
			type=EventType.THREAD_UPDATED,
			data={
				"id": str(thread_id),
				"last_activity_at": thread.last_activity_at.isoformat(),
				"updated_at": thread.updated_at.isoformat(),
			},
			user_id=owner_id,
			thread_id=str(thread_id),
		),
		origin_session_id=origin_session_id,
	)
