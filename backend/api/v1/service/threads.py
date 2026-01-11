"""Service helpers for threads and messages."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import overload

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.acl import AccessRole
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.schemas.message import MessageCreate
from api.schemas.sorting import CommonSortBy
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.v1.service import events as event_service
from api.v1.service import projects as project_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.chat.models import run_chat_model_json_schema
from api.v1.service.sorting import SortDir, apply_sort
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


def _ensure_admin_for_hidden(include_hidden: bool, principal: Principal) -> None:
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


class _ThreadMetadataOut(BaseModel):
	"""structured output schema for thread metadata generation."""

	title: str = Field(
		description="emoji followed by 1-3 lowercase words, e.g. '🔧 fix login bug'",
		max_length=50,
	)
	tags: list[str] = Field(
		default_factory=list,
		description="0-6 short lowercase tags",
		max_length=6,
	)


async def generate_thread_metadata(
	session: AsyncSession,
	*,
	thread_id: TypeID,
	chat_model: ChatModel,
	principal: Principal | None = None,
	replace: bool = False,
	emit_event: bool = True,
) -> Thread | None:
	"""generate thread metadata and persist via update_thread.

	when replace is false, only fills missing fields (title/tags).
	"""
	if principal is not None:
		await require_thread_access(
			str(thread_id),
			session,
			principal,
			required_role=AccessRole.EDITOR,
		)

	thread = await session.get(
		Thread,
		thread_id,
		options=[selectinload(Thread.messages), selectinload(Thread.owner)],
	)
	if not thread or thread.deleted_at or thread.is_temporary:
		return None

	existing_title = (thread.title or "").strip()
	has_title = existing_title != ""
	has_tags = bool(thread.tags) and len(thread.tags) > 0
	should_update_title = replace or not has_title
	should_update_tags = replace or not has_tags
	if not should_update_title and not should_update_tags:
		return None

	messages = sorted(thread.messages or [], key=lambda m: m.created_at)
	first_user = next((m for m in messages if m.type == MessageType.USER), None)
	first_assistant = next(
		(m for m in messages if m.type == MessageType.ASSISTANT), None
	)
	if not first_assistant:
		return None

	def extract_text(msg: Message | None) -> str:
		if not msg:
			return ""
		for part in msg.content or []:
			if isinstance(part, dict) and part.get("type") == "text":
				return str(part.get("text", ""))[:500]
		return ""

	payload = {
		"user": extract_text(first_user),
		"assistant": extract_text(first_assistant),
	}

	sdk_thread = SDKThread(
		messages=[
			SDKSystemMessage.from_text(
				"generate thread metadata. "
				"title must be: one emoji + 1-3 lowercase words. "
				"tags: 0-6 short lowercase labels. return only valid json."
			),
			SDKUserMessage.from_text(json.dumps(payload)),
		]
	)

	data = await run_chat_model_json_schema(
		chat_model,
		thread=sdk_thread,
		json_schema=_ThreadMetadataOut.model_json_schema(),
	)
	out = _ThreadMetadataOut.model_validate(data)

	desired_title = out.title.strip().lower() or None
	desired_tags = out.tags[:6]

	update_in = ThreadUpdate(
		title=(
			desired_title
			if should_update_title and desired_title != thread.title
			else None
		),
		tags=(
			desired_tags
			if should_update_tags and desired_tags != (thread.tags or [])
			else None
		),
	)
	if update_in.title is None and update_in.tags is None:
		return None

	if principal is None:
		owner = thread.owner or await session.get(User, thread.owner_id)
		if owner is None:
			return None
		principal = Principal(user=owner, group_ids=(), permissions=frozenset())

	return await update_thread(
		thread_id,
		update_in,
		session,
		principal=principal,
		emit_event=emit_event,
	)


async def list_thread_recipient_user_ids(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal | None = None,
	include_hidden: bool = False,
) -> list[str]:
	"""Return user ids that should receive notifications for this thread.

	This always includes the thread owner, even if there are no participants.
	When principal is provided, authz is checked. When None, runs unrestricted.
	"""
	if principal is not None:
		_ensure_admin_for_hidden(include_hidden, principal)
		thread = await _load_thread(
			thread_id,
			session,
			principal,
			required_role=AccessRole.VIEWER,
			include_hidden=include_hidden,
		)
	else:
		thread = await _load_thread(
			thread_id, session, None, include_hidden=include_hidden
		)

	participant_stmt = select(ThreadParticipant.user_id).where(
		ThreadParticipant.thread_id == thread_id,
		ThreadParticipant.user_id.isnot(None),
	)
	participant_result = await session.execute(participant_stmt)
	participant_ids = [str(uid) for uid in participant_result.scalars().all()]

	ordered_ids = [str(thread.owner_id), *participant_ids]
	seen: set[str] = set()
	unique_ids: list[str] = []
	for uid in ordered_ids:
		if uid in seen:
			continue
		seen.add(uid)
		unique_ids.append(uid)
	return unique_ids


@overload
async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
	include_hidden: bool = False,
) -> Thread: ...


@overload
async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: None = None,
	*,
	include_hidden: bool = False,
) -> Thread: ...


async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal | None = None,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
	include_hidden: bool = False,
) -> Thread:
	options = [selectinload(Thread.owner), selectinload(Thread.projects)]
	stmt = select(Thread).options(*options).where(Thread.id == thread_id)

	if principal is not None:
		stmt = stmt.where(
			thread_access_predicate(
				principal,
				required_role=required_role,
				include_hidden=include_hidden,
			)
		)
		if include_hidden:
			stmt = stmt.execution_options(include_deleted=True)
	else:
		if include_hidden:
			stmt = stmt.execution_options(include_deleted=True)
		else:
			stmt = stmt.where(
				Thread.deleted_at.is_(None), Thread.is_temporary.is_(False)
			)
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def create_thread(
	thread_in: ThreadCreate,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Thread:
	owner_id = thread_in.owner_id
	if not principal.is_admin:
		owner_id = TypeID(principal.user.id)
	else:
		owner = await session.get(User, owner_id)
		if not owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)

	projects = await project_service.load_projects(
		thread_in.project_ids, session, principal, required_role=AccessRole.EDITOR
	)
	thread_data = thread_in.model_dump(by_alias=True, exclude={"project_ids"})
	thread_data["owner_id"] = owner_id
	thread = Thread(**thread_data)
	thread.projects = projects
	session.add(thread)
	await session.flush()

	# emit thread.created event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=thread.id,
		type=EventType.THREAD_CREATED,
		data={
			"thread_id": str(thread.id),
			"title": thread.title,
			"owner_id": str(owner_id),
		},
		user_id=str(owner_id),
		thread_id=thread.id,
	)
	await event_service.publish_event(session, event=event)

	return await _load_thread(TypeID(thread.id), session, None, include_hidden=True)


async def list_threads(
	session: AsyncSession,
	*,
	principal: Principal,
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
	sort_by: str = "updated_at",
	sort_dir: SortDir = "desc",
	include_hidden: bool = False,
) -> list[Thread]:
	_ensure_admin_for_hidden(include_hidden, principal)
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(
			thread_access_predicate(
				principal,
				required_role=AccessRole.VIEWER,
				include_hidden=include_hidden,
			)
		)
	)

	if owner_id is not None:
		stmt = stmt.where(Thread.owner_id == owner_id)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)

	stmt = apply_sort(
		stmt,
		sort_by=sort_by,
		sort_dir=sort_dir,
		columns={
			"last_activity_at": Thread.last_activity_at,
			"created_at": Thread.created_at,
			"updated_at": Thread.updated_at,
			"title": Thread.title,
		},
		tie_breaker=Thread.id,
	)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def get_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> Thread:
	_ensure_admin_for_hidden(include_hidden, principal)
	return await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	emit_event: bool = True,
) -> Thread:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)
	update_data = thread_in.model_dump(exclude_unset=True, by_alias=True)
	new_owner_id = update_data.pop("owner_id", None)
	owner_changed = False
	if new_owner_id is not None and new_owner_id != thread.owner_id:
		if not principal.is_admin and thread.owner_id != principal.user.id:
			raise HTTPException(
				status_code=status.HTTP_403_FORBIDDEN,
				detail="forbidden",
			)
		new_owner = await session.get(User, new_owner_id)
		if not new_owner:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="User not found",
			)
		thread.owner_id = TypeID(new_owner_id)
		thread.owner = new_owner
		owner_changed = True

	project_ids = update_data.pop("project_ids", None)
	for field, value in update_data.items():
		setattr(thread, field, value)

	if project_ids is not None:
		thread.projects = await project_service.load_projects(
			project_ids, session, principal, required_role=AccessRole.EDITOR
		)

	await session.flush()

	# emit thread.updated event
	if emit_event:
		event = Event(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type=EventType.THREAD_UPDATED,
			data={
				"thread_id": str(thread.id),
				"title": thread.title,
				"owner_id": str(thread.owner_id),
				"updated_fields": list(thread_in.model_dump(exclude_unset=True).keys()),
			},
			user_id=str(thread.owner_id),
			thread_id=thread.id,
		)
		await event_service.publish_event(session, event=event)

	if (
		owner_changed
		and not principal.is_admin
		and str(new_owner_id) != str(principal.user.id)
	):
		return await _load_thread(thread_id, session, None)

	return await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
	)


async def delete_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)

	if not principal.is_admin and thread.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	owner_id = str(thread.owner_id)
	thread_title = thread.title

	thread.soft_delete()
	await session.flush()

	# emit thread.deleted event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=str(thread_id),
		type=EventType.THREAD_DELETED,
		data={
			"thread_id": str(thread_id),
			"title": thread_title,
		},
		user_id=owner_id,
		thread_id=str(thread_id),
	)
	await event_service.publish_event(session, event=event)


async def list_messages(
	thread_id: TypeID,
	session: AsyncSession,
	*,
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
		required_role=AccessRole.VIEWER,
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
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Event]:
	"""Return events associated with the given messages in this thread.

	authz is based on thread access (viewer+), not the global events permission.
	"""
	_ensure_admin_for_hidden(include_hidden, principal)
	await require_thread_access(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)

	if not message_ids:
		return []

	stmt = (
		select(Event)
		.where(
			Event.thread_id == str(thread_id),
			Event.message_id.in_([str(mid) for mid in message_ids]),
		)
		.order_by(Event.created_at)
		.limit(2000)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_message_tree(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""Return all messages in a thread as a flat list."""
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
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[Message]:
	"""Return the root→leaf path ending at thread.current_message_id."""
	_ensure_admin_for_hidden(include_hidden, principal)
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
	)
	if not thread.current_message_id:
		return []

	branch: list[Message] = []
	cur = await session.get(Message, thread.current_message_id)
	while cur is not None:
		branch.insert(0, cur)
		if not cur.parent_id:
			break
		cur = await session.get(Message, cur.parent_id)
	return branch


async def switch_branch(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> Thread:
	"""Set current_message_id to the deepest leaf descending from message_id."""
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
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
	await session.commit()
	return thread


async def create_message(
	thread_id: TypeID,
	message_in: MessageCreate,
	session: AsyncSession,
	*,
	principal: Principal,
	message_id: TypeID | None = None,
) -> Message:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
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
	if parent_id is None:
		parent_id = thread.current_message_id
	else:
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

	message = message_cls(
		thread_id=thread_id,
		parent_id=parent_id,
		**pk,
		**data,
	)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.flush()
	thread.current_message_id = message.id
	await session.commit()
	await session.refresh(message)
	return message


async def delete_user_message_turn(
	thread_id: TypeID,
	message_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
) -> None:
	"""delete a user message and its generated response(s) on the active branch.

	deletes the user message and all subsequent messages until (but not including)
	the next user message, if any.

	if a next user message exists, it will be re-parented to the deleted user's
	parent so the remaining branch stays connected.
	"""
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.EDITOR,
	)

	branch = await get_current_branch(
		thread_id,
		session,
		principal=principal,
		include_hidden=False,
	)
	if not branch:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Message not found",
		)

	start_idx: int | None = None
	for i, msg in enumerate(branch):
		if TypeID(msg.id) == message_id:
			start_idx = i
			break
	if start_idx is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Message not found",
		)

	start_msg = branch[start_idx]
	if start_msg.type != MessageType.USER:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="only user messages can be deleted",
		)

	end_idx = len(branch)
	for j in range(start_idx + 1, len(branch)):
		if branch[j].type == MessageType.USER:
			end_idx = j
			break

	parent_id = start_msg.parent_id

	# re-parent the next user message (if any) before deleting its ancestors
	if end_idx < len(branch):
		next_user = branch[end_idx]
		next_user.parent_id = parent_id
		await session.flush()

	# delete the message segment
	deleted_ids = {TypeID(m.id) for m in branch[start_idx:end_idx]}
	for msg in branch[start_idx:end_idx]:
		await session.delete(msg)

	# update thread leaf if needed
	if thread.current_message_id and TypeID(thread.current_message_id) in deleted_ids:
		if end_idx < len(branch):
			# leaf remains valid; keep current_message_id
			pass
			# note: we intentionally do not recompute leaf here; the remaining branch
			# still terminates at the existing leaf id.
		else:
			thread.current_message_id = parent_id

	thread.last_activity_at = datetime.now(tz=UTC)
	await session.commit()
