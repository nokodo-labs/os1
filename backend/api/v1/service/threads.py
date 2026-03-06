"""service helpers for threads and messages."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import overload

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.database import (
	build_cursor_page,
	decode_cursor,
	session_scope,
)
from api.models.access_rule import AccessLevel
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import Message, MessageType
from api.models.thread import Thread
from api.models.user import User
from api.permissions import ResourceType
from api.schemas.message import Message as MessageOut
from api.schemas.message import MessageCreate, MessageUpdate
from api.schemas.search import (
	CursorPage,
	SearchMode,
	SearchParams,
	SearchResultItem,
	SearchResultType,
)
from api.schemas.sorting import CommonSortBy
from api.schemas.thread import Thread as ThreadOut
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.settings import settings
from api.v1.service import events as event_service
from api.v1.service import projects as project_service
from api.v1.service import vectorstores as vectorstore_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	list_accessible_user_ids,
	require_permission,
	require_thread_access,
	thread_access_predicate,
)
from api.v1.service.chat.models import (
	resolve_task_chat_model,
	run_chat_model_json_schema,
)
from api.v1.service.embeddings import embed_text, embed_texts
from api.v1.service.sorting import SortDir, apply_sort
from api.v1.service.vectorize import (
	VectorSpec,
	build_chunk,
	fetch_acl_metadata,
	fetch_bulk_acl_metadata,
	remove_vectorized_resource,
	vectorize_resource,
)
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import UserMessage as SDKUserMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)


def _ensure_admin_for_hidden(include_hidden: bool, principal: Principal) -> None:
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


class _ThreadMetadataOut(BaseModel):
	"""structured output schema for thread metadata generation."""

	title: str = Field(
		description="emoji followed by 1-3 lowercase words.",
		max_length=50,
		examples=[
			"🧠 brainstorm new app features",
			"📚 research quantum computing",
			"🫂 help with friends",
		],
	)
	tags: list[str] = Field(
		default_factory=list,
		description="0-6 short lowercase tags",
		max_length=6,
	)


async def generate_thread_metadata(
	session: AsyncSession | None = None,
	*,
	thread_id: TypeID,
	principal: Principal,
	replace: bool = False,
	emit_event: bool = True,
	origin_session_id: str | None = None,
) -> Thread:
	"""generate thread metadata (title/tags) and persist via update_thread.

	when *replace* is false, only fills missing fields.
	when *session* is ``None`` (fire-and-forget), an independent session is
	created automatically.

	raises on failure - never returns ``None``.
	"""
	async with session_scope(session) as session:
		# auth: caller must have admin-level access on the thread
		await require_thread_access(
			str(thread_id),
			session,
			principal,
			required_level=AccessLevel.ADMIN,
		)

		chat_model = await resolve_task_chat_model(session, "thread_metadata")

		thread = await session.get(
			Thread,
			thread_id,
			options=[
				selectinload(Thread.messages),
				selectinload(Thread.projects),
			],
		)
		if not thread or thread.deleted_at or thread.is_temporary:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="thread not found or not eligible for metadata generation",
			)

		existing_title = (thread.title or "").strip()
		has_title = existing_title != ""
		has_tags = bool(thread.tags) and len(thread.tags) > 0
		should_update_title = replace or not has_title
		should_update_tags = replace or not has_tags
		if not should_update_title and not should_update_tags:
			return thread

		messages = sorted(thread.messages or [], key=lambda m: m.created_at)
		first_user = next((m for m in messages if m.type == MessageType.USER), None)
		first_assistant = next(
			(m for m in messages if m.type == MessageType.ASSISTANT), None
		)
		if not first_assistant:
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="cannot generate metadata: no assistant message in thread",
			)

		payload = {
			"user": first_user.text_content[:500] if first_user else "",
			"assistant": first_assistant.text_content[:500],
		}

		sdk_thread = SDKThread(
			messages=[
				SDKSystemMessage.from_text(
					"given the following chat history, generate thread metadata. "
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
			return thread

		result = await update_thread(
			thread_id,
			update_in,
			session,
			principal=principal,
			emit_event=emit_event,
			origin_session_id=origin_session_id,
		)

		# index thread with new metadata (title/tags + full message text for BM25)
		await session.refresh(thread, attribute_names=["messages"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=await fetch_acl_metadata(
				str(thread.id), ResourceType.THREAD, session
			),
		)

		return result


@overload
async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	required_level: AccessLevel = AccessLevel.READER,
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
	required_level: AccessLevel = AccessLevel.READER,
	include_hidden: bool = False,
) -> Thread:
	options = [
		selectinload(Thread.projects),
	]
	stmt = select(Thread).options(*options).where(Thread.id == thread_id)

	if principal is not None:
		stmt = stmt.where(
			thread_access_predicate(
				principal,
				required_level=required_level,
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
	origin_session_id: str | None = None,
) -> Thread:
	require_permission(principal, "threads:create")
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
		thread_in.project_ids, session, principal, required_level=AccessLevel.EDITOR
	)
	thread_data = thread_in.model_dump(by_alias=True, exclude={"project_ids"})
	thread_data["owner_id"] = owner_id
	thread = Thread(**thread_data)
	thread.projects = projects
	session.add(thread)
	await session.flush()
	await session.refresh(
		thread, attribute_names=["created_at", "updated_at", "last_activity_at"]
	)

	# emit thread.created event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=thread.id,
		type=EventType.THREAD_CREATED,
		data=ThreadOut.model_validate(thread).model_dump(mode="json"),
		user_id=str(owner_id),
		thread_id=thread.id,
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	return thread


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
	is_archived: bool | None = None,
) -> list[Thread]:
	_ensure_admin_for_hidden(include_hidden, principal)
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.projects),
		)
		.where(
			thread_access_predicate(
				principal,
				required_level=AccessLevel.READER,
				include_hidden=include_hidden,
			)
		)
	)

	if owner_id is not None:
		stmt = stmt.where(Thread.owner_id == owner_id)

	# always exclude temporary threads from listings
	if not include_hidden:
		stmt = stmt.where(Thread.is_temporary.is_(False))

	if is_archived is not None:
		stmt = stmt.where(Thread.is_archived == is_archived)

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
		required_level=AccessLevel.READER,
		include_hidden=include_hidden,
	)


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	emit_event: bool = True,
	origin_session_id: str | None = None,
) -> Thread:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
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

	# validate current_message_id belongs to this thread
	# TODO: verify perf impact. disabled until then.
	""" new_current_message_id = update_data.pop("current_message_id", None)
	if new_current_message_id is not None:
		msg = await session.get(Message, new_current_message_id)
		if not msg or msg.thread_id != thread_id:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Message not found in thread",
			)
		thread.current_message_id = new_current_message_id """

	project_ids = update_data.pop("project_ids", None)
	for field, value in update_data.items():
		setattr(thread, field, value)

	if project_ids is not None:
		thread.projects = await project_service.load_projects(
			project_ids, session, principal, required_level=AccessLevel.EDITOR
		)

	await session.flush()

	# emit thread.updated event
	if emit_event:
		await session.refresh(
			thread, attribute_names=["updated_at", "last_activity_at"]
		)
		# partial event: only changed fields + id + timestamps
		event_data = thread_in.model_dump(
			mode="json", exclude_unset=True, by_alias=True
		)
		event_data.pop("project_ids", None)
		event_data["id"] = str(thread.id)
		event_data["updated_at"] = thread.updated_at.isoformat()
		event_data["last_activity_at"] = thread.last_activity_at.isoformat()
		if project_ids is not None:
			event_data["projects"] = [
				{"id": str(p.id), "name": p.name} for p in thread.projects
			]
		event = Event(
			scope=EventScope.THREAD,
			scope_id=thread.id,
			type=EventType.THREAD_UPDATED,
			data=event_data,
			user_id=str(thread.owner_id),
			thread_id=thread.id,
		)
		await event_service.publish_event(
			session, event=event, origin_session_id=origin_session_id
		)

	# re-index if searchable fields changed
	if await THREAD_SPEC.should_revectorize(thread, thread_in, session):
		await session.refresh(thread, attribute_names=["messages"])
		await vectorize_resource(
			spec=THREAD_SPEC,
			resource=thread,
			session=session,
			extra_metadata=await fetch_acl_metadata(
				str(thread.id), ResourceType.THREAD, session
			),
		)

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
		required_level=AccessLevel.READER,
	)


async def delete_thread(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> None:
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_level=AccessLevel.EDITOR,
	)

	if not principal.is_admin and thread.owner_id != principal.user.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)

	owner_id = str(thread.owner_id)

	if settings.soft_delete.threads:
		thread.soft_delete()
	else:
		await session.delete(thread)
	await session.flush()

	# emit thread.deleted event
	event = Event(
		scope=EventScope.THREAD,
		scope_id=str(thread_id),
		type=EventType.THREAD_DELETED,
		data={"id": str(thread_id)},
		user_id=owner_id,
		thread_id=str(thread_id),
	)
	await event_service.publish_event(
		session, event=event, origin_session_id=origin_session_id
	)

	await remove_vectorized_resource(
		THREAD_SPEC, resource_id=str(thread_id), session=session
	)


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
	*,
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
	*,
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
	*,
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

	return await _walk_branch_cte(session, thread.current_message_id)


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
	*,
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
	*,
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

	await session.commit()
	return thread


async def create_message(
	thread_id: TypeID,
	message_in: MessageCreate,
	session: AsyncSession,
	*,
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
	await session.commit()

	# emit message.created event with full message payload
	message_data = MessageOut.model_validate(message).model_dump(
		mode="json",
	)
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MESSAGE_CREATED,
		data=message_data,
		user_id=principal.user_id,
		thread_id=str(thread_id),
		message_id=str(message.id),
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	return message


async def update_user_message(
	thread_id: TypeID,
	message_id: TypeID,
	message_in: MessageUpdate,
	session: AsyncSession,
	*,
	principal: Principal,
	origin_session_id: str | None = None,
) -> Message:
	await _load_thread(
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
	for field, value in update_data.items():
		setattr(message, field, value)
	await session.flush()
	await session.commit()
	await session.refresh(message)

	message_data = MessageOut.model_validate(message).model_dump(mode="json")
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MESSAGE_UPDATED,
		data=message_data,
		user_id=principal.user_id,
		thread_id=str(thread_id),
		message_id=str(message.id),
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)
	return message


async def _find_deepest_leaf(
	session: AsyncSession,
	thread_id: TypeID,
	start_id: str | None,
	*,
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
	*,
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

	# bulk-delete subtree; DB CASCADE on event FKs handles cleanup
	await session.execute(sa_delete(Message).where(Message.id.in_(deleted_ids)))

	# emit message.deleted event
	event = Event(
		scope=EventScope.USER,
		scope_id=principal.user_id,
		type=EventType.MESSAGE_DELETED,
		data={
			"thread_id": str(thread_id),
			"message_id": str(message_id),
			"parent_id": parent_id,
			"deleted_ids": deleted_ids,
		},
		user_id=principal.user_id,
		thread_id=str(thread_id),
	)
	await event_service.publish_event(
		session,
		event=event,
		origin_session_id=origin_session_id,
	)

	await session.commit()


async def handle_typing_event(
	*,
	session: AsyncSession,
	user_id: str,
	thread_id: str,
	typing: bool,
) -> None:
	"""broadcast a typing indicator to all users with access to a thread.

	ephemeral: no event persistence, just fan-out over WS.
	the sender must be among the accessible users; if not, the event is
	silently dropped (prevents spam for threads the user has no access to).
	"""
	recipient_ids = await list_accessible_user_ids(
		ResourceType.THREAD,
		thread_id,
		session,
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

	await event_service.event_connections.send_to_users(
		recipient_ids,
		payload,
		exclude_user_id=user_id,
	)


def _thread_dense_text(thread: Thread) -> str:
	parts: list[str] = []
	if thread.title:
		parts.append(thread.title)
	summary = (thread.metadata_ or {}).get("summary")
	if summary:
		parts.append(str(summary))
	return " ".join(parts).strip()


def _thread_bm25_text(thread: Thread) -> str:
	dense = _thread_dense_text(thread)
	parts = [dense] if dense else []
	if thread.messages:
		msg_text = " ".join(
			m.text_content
			for m in thread.messages
			if m.type in (MessageType.USER, MessageType.ASSISTANT) and m.text_content
		)
		if msg_text:
			parts.append(msg_text)
	return " ".join(parts).strip()


def _thread_metadata(thread: Thread) -> JSONObject:
	return {
		"resource_type": "thread",
		"owner_id": str(thread.owner_id),
		"title": thread.title or "",
		"tags": list(thread.tags or []),
		"is_archived": thread.is_archived,
		# acl fields - populated at vectorize time from access_rules table
		"allowed_user_ids": [],
		"allowed_group_ids": [],
		"allowed_role_ids": [],
	}


async def _thread_should_revectorize(
	thread: Thread,
	thread_in: ThreadUpdate,
	session: AsyncSession,
) -> bool:
	# title/tags are metadata-only; summary change is detected via metadata_ key
	_fields = {"title", "tags", "metadata_"}
	update_data = thread_in.model_dump(exclude_unset=True, mode="python")
	return bool(_fields & update_data.keys())


THREAD_SPEC: VectorSpec[Thread] = VectorSpec(
	resource_type="thread",
	resource_id=lambda t: str(t.id),
	dense_text=_thread_dense_text,
	bm25_text=_thread_bm25_text,
	metadata=_thread_metadata,
	should_revectorize=_thread_should_revectorize,
	sort_key="updated_at",
)


async def vectorize_all_threads(session: AsyncSession) -> int:
	"""vectorize all non-deleted, non-temporary threads in bulk. returns count."""
	stmt = (
		select(Thread)
		.where(
			Thread.deleted_at.is_(None),
			Thread.is_temporary.is_(False),
		)
		.options(selectinload(Thread.messages))
	)
	result = await session.execute(stmt)
	valid: list[tuple[Thread, str]] = []
	for th in result.scalars().unique().all():
		text = _thread_dense_text(th)
		if text.strip():
			valid.append((th, text))
	if not valid:
		return 0
	embeddings = await embed_texts([text for _, text in valid], session)
	thread_ids = [str(t.id) for t, _ in valid]
	acl_by_id = await fetch_bulk_acl_metadata(thread_ids, ResourceType.THREAD, session)
	chunks = []
	for (thread, _), emb in zip(valid, embeddings):
		await remove_vectorized_resource(
			spec=THREAD_SPEC, resource_id=str(thread.id), session=session
		)
		acl = acl_by_id.get(str(thread.id))
		chunks.append(build_chunk(THREAD_SPEC, thread, emb, extra_metadata=acl))
	await vectorstore_service.upsert_chunks(chunks=chunks, session=session)
	return len(valid)


async def _autocomplete_threads(
	q: str,
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 5,
) -> list[SearchResultItem]:
	"""pg_trgm autocomplete for threads on title."""
	stmt = (
		select(Thread)
		.where(
			Thread.is_temporary.is_(False),
			thread_access_predicate(
				principal,
				required_level=AccessLevel.READER,
				include_hidden=False,
			),
			or_(
				func.similarity(Thread.title, q) > 0.1,
				Thread.title.ilike(f"%{q}%"),
			),
		)
		.order_by(func.similarity(Thread.title, q).desc())
		.limit(limit)
	)
	result = await db.execute(stmt)
	return [
		SearchResultItem(
			type=SearchResultType.THREAD,
			id=TypeID(t.id),
			title=t.title or "",
			subtitle=None,
			created_at=t.created_at,
			updated_at=t.updated_at,
		)
		for t in result.scalars().unique().all()
	]


async def _hybrid_search_threads(
	query_text: str,
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 10,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> list[SearchResultItem]:
	"""qdrant hybrid search for threads (dense + BM25)."""
	params = search_params or SearchParams()
	need_dense = params.mode in (SearchMode.DENSE, SearchMode.HYBRID, SearchMode.FULL)
	need_sparse = params.mode in (SearchMode.SPARSE, SearchMode.HYBRID, SearchMode.FULL)
	query_emb = (
		query_embedding
		if query_embedding is not None
		else (await embed_text(text=query_text, session=db) if need_dense else None)
	)
	text_query = query_text if need_sparse else None
	# acl-based qdrant filter: owner or explicit grant - solves broad-surface problem
	# principals with default access bypass should-conditions (role or global defaults)
	query_filter = vectorstore_service.acl_filter(
		"thread",
		is_admin=(
			principal.is_admin or principal.has_default_access(ResourceType.THREAD)
		),
		user_id=str(principal.user.id),
		group_ids=principal.group_ids,
		role_ids=principal.role_ids,
	)
	results = await vectorstore_service.search(
		session=db,
		query=query_emb,
		text_query=text_query,
		limit=limit,
		query_filter=query_filter,
		normalize=params.normalize,
	)
	if not results:
		return []
	resource_ids = [r.metadata["resource_id"] for r in results]
	stmt = select(Thread).where(
		Thread.id.in_(resource_ids),
		Thread.deleted_at.is_(None),
		Thread.is_temporary.is_(False),
		thread_access_predicate(
			principal,
			required_level=AccessLevel.READER,
			include_hidden=False,
		),
	)
	db_result = await db.execute(stmt)
	by_id = {str(t.id): t for t in db_result.scalars().unique().all()}
	score_by_rid = {str(r.metadata["resource_id"]): r.score for r in results}
	items: list[SearchResultItem] = []
	for r in results:
		rid = str(r.metadata["resource_id"])
		thread = by_id.get(rid)
		if not thread:
			continue
		summary = (thread.metadata_ or {}).get("summary")
		items.append(
			SearchResultItem(
				type=SearchResultType.THREAD,
				id=TypeID(thread.id),
				title=thread.title or "",
				subtitle=(str(summary)[:100] if summary else None),
				score=score_by_rid.get(rid),
				created_at=thread.created_at,
				updated_at=thread.updated_at,
			)
		)
	return items


async def search_threads(
	query_text: str,
	db: AsyncSession,
	*,
	principal: Principal,
	limit: int = 10,
	cursor: str | None = None,
	search_params: SearchParams | None = None,
	query_embedding: list[float] | None = None,
) -> CursorPage[SearchResultItem]:
	"""parallel pg_trgm + qdrant hybrid search with cursor pagination."""
	params = search_params or SearchParams()
	coros: list[Coroutine[None, None, list[SearchResultItem]]] = []
	run_autocomplete = params.mode in (
		SearchMode.AUTOCOMPLETE,
		SearchMode.FULL,
	)
	run_hybrid = params.mode in (
		SearchMode.HYBRID,
		SearchMode.DENSE,
		SearchMode.SPARSE,
		SearchMode.FULL,
	)
	# hybrid first - wins on deduplication (higher quality than autocomplete)
	if run_hybrid:
		coros.append(
			_hybrid_search_threads(
				query_text,
				db,
				principal=principal,
				limit=limit + 1,
				search_params=params,
				query_embedding=query_embedding,
			)
		)
	if run_autocomplete:
		coros.append(
			_autocomplete_threads(query_text, db, principal=principal, limit=limit + 1)
		)
	results = await asyncio.gather(*coros, return_exceptions=True)
	items = vectorstore_service.merge_deduplicate(
		results, limit + 1, resource_name="threads"
	)
	if cursor:
		ts, cid = decode_cursor(cursor)
		_sk = THREAD_SPEC.sort_key
		items = [i for i in items if (getattr(i, _sk), str(i.id)) < (ts, cid)]
	_sk = THREAD_SPEC.sort_key
	items.sort(key=lambda r: (getattr(r, _sk), str(r.id)), reverse=True)
	return build_cursor_page(items, limit, sort_key=THREAD_SPEC.sort_key)
