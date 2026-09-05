"""flat message reads: listings, point reads, and per-message events."""

import binascii
import json
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import decode_cursor, encode_cursor
from api.models.access_rule import AccessLevel
from api.models.event import Event
from api.models.event_types import EventType
from api.models.message import Message, MessageType
from api.permissions import ActionPermission
from api.schemas.event import EventPage
from api.schemas.sorting import CommonSortBy
from api.v1.service.authentication import Principal
from api.v1.service.authorization import (
	require_permission,
	require_thread_access,
)
from api.v1.service.listing import SortDir, apply_sort
from api.v1.service.threads.common import (
	ensure_admin_for_hidden_or_deleted,
	message_load_options,
)
from api.v1.service.threads.tree import visible_message_ids
from nokodo_ai.utils.typeid import TypeID


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
	include_deleted: bool = False,
) -> list[Message]:
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)
	visible = (await visible_message_ids(session, [thread_id])).get(
		str(thread_id), set()
	)
	if not visible:
		return []
	base_stmt = (
		select(Message)
		.where(Message.thread_id == thread_id, Message.id.in_(visible))
		.options(*message_load_options())
	)
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
			Message.id.in_(visible),
			Message.type == MessageType.ASSISTANT,
			boundary_predicate,
		)
		.order_by(Message.created_at.desc(), Message.id.desc())
		.options(*message_load_options())
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


async def get_message(
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> Message:
	"""get a message by id after validating chat access."""
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	result = await session.execute(
		select(Message).where(Message.id == message_id).options(*message_load_options())
	)
	message = result.scalar_one_or_none()
	if message is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	await require_thread_access(
		message.thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)
	return message


async def list_events_for_message_ids(
	thread_id: TypeID,
	message_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	include_deleted: bool = False,
	event_types: list[EventType] | None = None,
	limit: int = 500,
	cursor: str | None = None,
) -> EventPage:
	"""return a page of events associated with the given messages in this thread.

	authz is based on thread access (viewer+), not the global events permission.
	when event_types is provided, only events of those types are returned.

	a single message can accumulate an unbounded number of events (nothing
	reaps the table, and per-second progress emitters anchor on one message),
	so this pages on the (created_at, id) keyset rather than capping the
	result: a caller that wants everything follows next_cursor and knows when
	it is done, instead of silently receiving less than it asked for.
	"""
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)

	if not message_ids:
		return EventPage(items=[])

	conditions = [
		Event.thread_id == str(thread_id),
		Event.message_id.in_([str(mid) for mid in message_ids]),
	]
	if event_types:
		conditions.append(Event.type.in_(event_types))
	if cursor:
		try:
			after_created_at, after_id = decode_cursor(cursor)
		except (ValueError, KeyError, binascii.Error, json.JSONDecodeError) as exc:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="invalid cursor",
			) from exc
		if not isinstance(after_created_at, datetime):
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="invalid cursor",
			)
		conditions.append(
			(Event.created_at > after_created_at)
			| ((Event.created_at == after_created_at) & (Event.id > after_id))
		)

	# over-fetch one row to detect a further page without a second query.
	stmt = (
		select(Event)
		.where(*conditions)
		.order_by(Event.created_at, Event.id)
		.limit(limit + 1)
	)
	rows = list((await session.execute(stmt)).scalars().all())

	has_more = len(rows) > limit
	items = rows[:limit]
	next_cursor = (
		encode_cursor(items[-1].created_at, str(items[-1].id))
		if has_more and items
		else None
	)
	return EventPage(items=items, next_cursor=next_cursor, has_more=has_more)


async def list_message_tree(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_hidden: bool = False,
	include_deleted: bool = False,
) -> list[Message]:
	"""return all messages in a thread as a flat list. threads operators only.

	unbounded by design, which is why it is an operator debugging surface and
	never a client loading path - clients page.
	"""
	require_permission(principal, ActionPermission.THREADS_MANAGE)
	ensure_admin_for_hidden_or_deleted(include_hidden, include_deleted, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
		include_deleted=include_deleted,
	)
	stmt = (
		select(Message)
		.where(Message.thread_id == thread_id)
		.options(*message_load_options())
		.order_by(Message.created_at, Message.id)
	)
	return list((await session.execute(stmt)).scalars().all())
