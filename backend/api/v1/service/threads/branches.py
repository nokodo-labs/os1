"""paging, sibling navigation, and canon switching for message branches."""

import base64
import binascii
import json

from fastapi import HTTPException, status
from sqlalchemy import func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.database.advisory_locks import acquire_resource_write_lock
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message
from api.models.thread import Thread
from api.models.thread_summary import SummaryPurpose
from api.permissions import ActionPermission, ResourceType
from api.schemas.thread import BranchPage, SiblingBranchCount
from api.v1.service.authentication import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.events import persist_and_fanout_event
from api.v1.service.resource_payload_cache import invalidate_resource_payload_cache
from api.v1.service.threads.common import (
	is_multi_writer_thread,
	load_thread,
	message_load_options,
)
from api.v1.service.threads.splices import clear_pointers_on_canon
from api.v1.service.threads.summaries import delete_stale_summaries_for_thread
from api.v1.service.threads.tree import (
	branch_depths_cte,
	canon_message_ids,
	deepest_leaf_from,
	resolve_message_branch,
	walk_to_root,
)
from nokodo_ai.utils.typeid import TypeID


SIBLING_FANOUT_CAP = 5
"""how many alternatives one message contributes to a page."""


def _sibling_selector(multi_writer: bool):
	"""filter sibling branches according to the thread conversation model."""
	if multi_writer:
		return Message.branch_current_message_id.is_not(None)
	return literal(True)


async def _page_siblings(
	session: AsyncSession,
	messages: list[Message],
	multi_writer: bool,
	leaf_id: TypeID,
	branch_root_id: TypeID | None,
) -> tuple[list[Message], list[SiblingBranchCount]]:
	"""load capped sibling roots and true sibling counts for one page."""
	if not messages:
		return [], []
	parent_ids = [message.id for message in messages]
	branch = branch_depths_cte(leaf_id, root_id=branch_root_id)
	on_branch = select(branch.c.msg_id)
	ranked = (
		select(
			Message.id.label("msg_id"),
			Message.parent_id.label("parent_id"),
			Message.id.in_(on_branch).label("on_branch"),
			func.row_number()
			.over(
				partition_by=Message.parent_id,
				order_by=(Message.created_at, Message.id),
			)
			.label("position"),
			func.count().over(partition_by=Message.parent_id).label("branch_total"),
		)
		.where(
			Message.parent_id.in_(parent_ids),
			_sibling_selector(multi_writer),
		)
		.subquery()
	)
	rows = (
		await session.execute(
			select(
				ranked.c.msg_id,
				ranked.c.parent_id,
				ranked.c.branch_total,
				ranked.c.position,
				ranked.c.on_branch,
			).where(ranked.c.on_branch | (ranked.c.position <= SIBLING_FANOUT_CAP))
		)
	).all()
	if not rows:
		return [], []
	carried = [
		msg_id
		for msg_id, _parent_id, _total, position, on_branch_flag in rows
		if not on_branch_flag and position <= SIBLING_FANOUT_CAP
	]
	forked_parents = {
		parent_id
		for _msg_id, parent_id, _total, _position, on_branch_flag in rows
		if not on_branch_flag
	}
	counts = [
		SiblingBranchCount(parent_id=parent_id, total=total)
		for parent_id, total in sorted(
			{
				parent_id: int(total)
				for _msg_id, parent_id, total, _position, _flag in rows
				if parent_id in forked_parents
			}.items()
		)
	]
	if not carried:
		return [], counts
	loaded = (
		await session.execute(
			select(Message)
			.where(Message.id.in_(carried))
			.options(*message_load_options())
			.order_by(Message.created_at, Message.id)
		)
	).scalars()
	return list(loaded), counts


def _encode_branch_cursor(message_id: TypeID, toward_root: bool) -> str:
	"""encode a stable page boundary using a message id."""
	payload = {"m": str(message_id), "r": toward_root}
	return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_branch_cursor(cursor: str) -> tuple[TypeID, bool]:
	"""decode a branch page boundary and direction."""
	try:
		payload = json.loads(base64.urlsafe_b64decode(cursor))
		return TypeID(payload["m"]), bool(payload["r"])
	except (ValueError, KeyError, TypeError, binascii.Error) as exc:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="malformed cursor",
		) from exc


async def get_branch_page(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 50,
	anchor_message_id: TypeID | None = None,
	before: int | None = None,
	after: int | None = None,
	cursor: str | None = None,
) -> BranchPage:
	"""return one SQL-windowed page of a selected message branch."""
	if anchor_message_id is None and (before is not None or after is not None):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="before/after require anchor_message_id",
		)
	if cursor is not None and (skip or anchor_message_id is not None):
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="cursor cannot be combined with skip or anchor_message_id",
		)
	if anchor_message_id is not None and skip:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="skip does not apply to an anchored page",
		)
	if (before or 0) + (after or 0) >= 200:
		raise HTTPException(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			detail="before + after window exceeds the page cap of 200",
		)
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)
	multi_writer = await is_multi_writer_thread(session, thread_id)
	leaf_id = thread.current_message_id
	branch_root_id: TypeID | None = None
	if anchor_message_id is not None:
		anchor = await session.get(Message, anchor_message_id)
		if anchor is None or anchor.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="message not found in this thread",
			)
		canon_ids = await canon_message_ids(session, thread_id)
		if str(anchor_message_id) not in canon_ids:
			branch = (
				await resolve_message_branch(session, anchor_message_id, canon_ids)
				if multi_writer
				else None
			)
			if branch is not None:
				branch_root_id = branch.root_id
				leaf_id = branch.leaf_id
			elif multi_writer:
				raise HTTPException(
					status_code=status.HTTP_404_NOT_FOUND,
					detail="message not found in this thread",
				)
			else:
				leaf_id = await deepest_leaf_from(session, thread_id, anchor_message_id)
	if leaf_id is None:
		return BranchPage(messages=[], total=0, skip=0, siblings=[], sibling_counts=[])

	branch = branch_depths_cte(leaf_id, root_id=branch_root_id)
	total = await session.scalar(select(func.count()).select_from(branch)) or 0
	if anchor_message_id is not None:
		anchor_depth = await session.scalar(
			select(branch.c.depth).where(branch.c.msg_id == anchor_message_id)
		)
		if anchor_depth is None:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="message not found in this thread",
			)
		if before is not None or after is not None:
			low = max(anchor_depth - (after or 0), 0)
			high = anchor_depth + (before or 0)
		else:
			low = (anchor_depth // limit) * limit
			high = low + limit - 1
	elif cursor is not None:
		boundary_id, toward_root = _decode_branch_cursor(cursor)
		boundary_depth = await session.scalar(
			select(branch.c.depth).where(branch.c.msg_id == boundary_id)
		)
		if boundary_depth is None:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
				detail="cursor does not point into this branch",
			)
		if toward_root:
			low = boundary_depth + 1
			high = low + limit - 1
		else:
			high = max(boundary_depth - 1, 0)
			low = max(high - limit + 1, 0)
	else:
		low = skip
		high = skip + limit - 1

	stmt = (
		select(Message)
		.join(branch, Message.id == branch.c.msg_id)
		.where(branch.c.depth >= low, branch.c.depth <= high)
		.options(*message_load_options())
		.order_by(branch.c.depth.desc())
	)
	messages = list((await session.execute(stmt)).scalars().all())
	siblings, sibling_counts = await _page_siblings(
		session, messages, multi_writer, leaf_id, branch_root_id
	)
	root_end = messages[0].id if messages else None
	leaf_end = messages[-1].id if messages else None
	return BranchPage(
		messages=messages,
		total=total,
		skip=low,
		siblings=siblings,
		sibling_counts=sibling_counts,
		cursor_toward_root=(
			_encode_branch_cursor(root_end, toward_root=True)
			if root_end is not None and low + len(messages) < total
			else None
		),
		cursor_toward_leaf=(
			_encode_branch_cursor(leaf_end, toward_root=False)
			if leaf_end is not None and low > 0
			else None
		),
	)


async def list_message_siblings(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	skip: int = 0,
	limit: int = 50,
) -> list[Message]:
	"""page the branches hanging off one message, oldest first."""
	await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.READER,
	)
	parent = await session.get(Message, message_id)
	if parent is None or parent.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found in this thread",
		)
	multi_writer = await is_multi_writer_thread(session, thread_id)
	stmt = (
		select(Message)
		.where(
			Message.parent_id == message_id,
			_sibling_selector(multi_writer),
		)
		.options(*message_load_options())
		.order_by(Message.created_at, Message.id)
		.offset(skip)
		.limit(limit)
	)
	return list((await session.execute(stmt)).scalars().all())


async def switch_branch(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Thread:
	"""select a branch as canon while preserving the outgoing selected path."""
	thread = await load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)
	if await is_multi_writer_thread(session, thread_id):
		require_permission(principal, ActionPermission.THREADS_MANAGE)
	await acquire_resource_write_lock(session, "thread", thread_id)
	message = await session.get(Message, message_id)
	if message is None or message.thread_id != thread_id:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="message not found",
		)
	leaf_id = await deepest_leaf_from(session, thread_id, message_id)
	old_head_id = thread.current_message_id
	if old_head_id is not None and leaf_id is not None and leaf_id != old_head_id:
		old_path = await walk_to_root(session, old_head_id)
		new_path_ids = {
			path_message_id
			for path_message_id, _parent_id, _branch_current_id in await walk_to_root(
				session, leaf_id
			)
		}
		outgoing_ids: list[TypeID] = []
		for path_message_id, _parent_id, _branch_current_id in old_path:
			if path_message_id in new_path_ids:
				break
			outgoing_ids.append(path_message_id)
		if outgoing_ids:
			await session.execute(
				update(Message)
				.where(Message.id == outgoing_ids[-1])
				.values(
					branch_current_message_id=old_head_id,
					updated_at=Message.updated_at,
				)
			)
	thread.current_message_id = leaf_id
	await clear_pointers_on_canon(session, leaf_id)
	await delete_stale_summaries_for_thread(
		thread_id,
		session,
		purpose=SummaryPurpose.CATALOG,
		active_end_message_id=leaf_id,
	)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user.id,
		type=EventType.THREAD_UPDATED,
		data={
			"id": str(thread_id),
			"current_message_id": str(leaf_id),
		},
		user_id=principal.user.id,
		thread_id=thread_id,
	)
	await persist_and_fanout_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	try:
		await session.commit()
	except IntegrityError as exc:
		await session.rollback()
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="branch state changed concurrently; please retry",
		) from exc
	await invalidate_resource_payload_cache(ResourceType.THREAD, thread_id)
	return thread
