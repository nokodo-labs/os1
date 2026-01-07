"""Service helpers for threads and messages."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.acl import AccessRole
from api.models.event import Event, EventScope
from api.models.event_types import EventType
from api.models.message import (
	AssistantMessage,
	Message,
	MessageType,
	SystemMessage,
	ToolMessage,
	UserMessage,
)
from api.models.project import Project
from api.models.thread import Thread
from api.models.thread_participant import ThreadParticipant
from api.models.user import User
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate, ThreadUpdate
from api.v1.service import events as event_service
from api.v1.service.auth import Principal
from api.v1.service.authorization import (
	project_access_predicate,
	require_thread_access,
	thread_access_predicate,
)
from nokodo_ai.utils.typeid import TypeID


def _ensure_admin_for_hidden(include_hidden: bool, principal: Principal) -> None:
	if include_hidden and not principal.is_admin:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="forbidden",
		)


async def list_thread_recipient_user_ids(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	principal: Principal,
	include_hidden: bool = False,
) -> list[str]:
	"""Return user ids that should receive notifications for this thread.

	This always includes the thread owner, even if there are no participants.
	authz is based on thread access (viewer+).
	"""
	_ensure_admin_for_hidden(include_hidden, principal)
	thread = await _load_thread(
		thread_id,
		session,
		principal,
		required_role=AccessRole.VIEWER,
		include_hidden=include_hidden,
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


async def _load_thread(
	thread_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.VIEWER,
	include_hidden: bool = False,
) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(Thread.id == thread_id)
		.where(
			thread_access_predicate(
				principal,
				required_role=required_role,
				include_hidden=include_hidden,
			)
		)
	)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)
	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _load_thread_unrestricted(
	thread_id: TypeID,
	session: AsyncSession,
	*,
	include_hidden: bool = False,
) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(Thread.id == thread_id)
	)

	if include_hidden:
		stmt = stmt.execution_options(include_deleted=True)
	else:
		stmt = stmt.where(Thread.deleted_at.is_(None), Thread.is_temporary.is_(False))

	result = await session.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _ensure_user(user_id: TypeID, session: AsyncSession) -> None:
	user = await session.get(User, user_id)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)


async def _load_projects(
	project_ids: list[TypeID],
	session: AsyncSession,
	principal: Principal,
	*,
	required_role: AccessRole = AccessRole.EDITOR,
) -> list[Project]:
	if not project_ids:
		return []

	stmt = select(Project).where(Project.id.in_(project_ids))
	stmt = stmt.where(project_access_predicate(principal, required_role=required_role))
	result = await session.scalars(stmt)
	projects = list(result.all())
	found = {project.id for project in projects}
	missing = [project_id for project_id in project_ids if project_id not in found]
	if missing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Projects not found: {missing}",
		)
	return projects


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
		await _ensure_user(owner_id, session)

	projects = await _load_projects(thread_in.project_ids, session, principal)
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

	return await _load_thread_unrestricted(
		TypeID(thread.id),
		session,
		include_hidden=True,
	)


async def list_threads(
	session: AsyncSession,
	*,
	principal: Principal,
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
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
		.order_by(Thread.last_activity_at.desc())
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
		thread.projects = await _load_projects(project_ids, session, principal)

	await session.flush()

	# emit thread.updated event
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
		return await _load_thread_unrestricted(thread_id, session)

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
	stmt = (
		select(Message)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


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

	match message_in.type:
		case MessageType.USER:
			message = UserMessage(
				thread_id=thread_id,
				parent_id=parent_id,
				**pk,
				**data,
			)
		case MessageType.ASSISTANT:
			message = AssistantMessage(
				thread_id=thread_id,
				parent_id=parent_id,
				**pk,
				**data,
			)
		case MessageType.TOOL:
			message = ToolMessage(
				thread_id=thread_id,
				parent_id=parent_id,
				**pk,
				**data,
			)
		case MessageType.SYSTEM:
			message = SystemMessage(
				thread_id=thread_id,
				parent_id=parent_id,
				**pk,
				**data,
			)
		case _:
			message = UserMessage(
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
