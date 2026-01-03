"""Service helpers for threads and messages."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.acl import AccessRole
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
from api.models.user import User
from api.schemas.message import MessageCreate
from api.schemas.thread import ThreadCreate, ThreadUpdate
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
	await session.commit()
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

	await session.commit()
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

	thread.soft_delete()
	await session.commit()


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

	match message_in.type:
		case MessageType.USER:
			message = UserMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.ASSISTANT:
			message = AssistantMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.TOOL:
			message = ToolMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case MessageType.SYSTEM:
			message = SystemMessage(thread_id=thread_id, parent_id=parent_id, **data)
		case _:
			message = UserMessage(thread_id=thread_id, parent_id=parent_id, **data)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.flush()
	thread.current_message_id = message.id
	await session.commit()
	await session.refresh(message)
	return message
