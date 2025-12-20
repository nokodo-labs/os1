"""Service helpers for threads and messages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from api.typeid import TypeID


async def _load_thread(thread_id: TypeID, session: AsyncSession) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.where(Thread.id == thread_id)
	)
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
) -> list[Project]:
	if not project_ids:
		return []

	result = await session.scalars(select(Project).where(Project.id.in_(project_ids)))
	projects = list(result.all())
	found = {project.id for project in projects}
	missing = [project_id for project_id in project_ids if project_id not in found]
	if missing:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Projects not found: {missing}",
		)
	return projects


async def create_thread(thread_in: ThreadCreate, session: AsyncSession) -> Thread:
	await _ensure_user(thread_in.owner_id, session)
	projects = await _load_projects(thread_in.project_ids, session)
	thread = Thread(**thread_in.model_dump(by_alias=True, exclude={"project_ids"}))
	thread.projects = projects
	session.add(thread)
	await session.commit()
	return await _load_thread(cast(TypeID, thread.id), session)


async def list_threads(
	session: AsyncSession,
	owner_id: TypeID | None = None,
	skip: int = 0,
	limit: int = 20,
) -> list[Thread]:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.projects),
		)
		.order_by(Thread.last_activity_at.desc())
	)

	if owner_id is not None:
		stmt = stmt.where(Thread.owner_id == owner_id)

	result = await session.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


async def get_thread(thread_id: TypeID, session: AsyncSession) -> Thread:
	return await _load_thread(thread_id, session)


async def update_thread(
	thread_id: TypeID,
	thread_in: ThreadUpdate,
	session: AsyncSession,
) -> Thread:
	thread = await _load_thread(thread_id, session)
	update_data = thread_in.model_dump(exclude_unset=True, by_alias=True)
	new_owner_id = update_data.get("owner_id")
	if new_owner_id is not None:
		await _ensure_user(new_owner_id, session)

	project_ids = update_data.pop("project_ids", None)
	for field, value in update_data.items():
		setattr(thread, field, value)

	if project_ids is not None:
		thread.projects = await _load_projects(project_ids, session)

	await session.commit()
	return await _load_thread(thread_id, session)


async def list_messages(
	thread_id: TypeID,
	session: AsyncSession,
	skip: int = 0,
	limit: int = 100,
) -> list[Message]:
	await _load_thread(thread_id, session)
	stmt = (
		select(Message)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at)
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_message_tree(thread_id: TypeID, session: AsyncSession) -> list[Message]:
	"""Return all messages in a thread as a flat list."""
	return await list_messages(thread_id, session, skip=0, limit=10_000)


async def get_current_branch(thread_id: TypeID, session: AsyncSession) -> list[Message]:
	"""Return the root→leaf path ending at thread.current_message_id."""
	thread = await _load_thread(thread_id, session)
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
) -> Thread:
	"""Set current_message_id to the deepest leaf descending from message_id."""
	thread = await _load_thread(thread_id, session)
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
		leaf_id = cast(TypeID, children[-1].id)

	thread.current_message_id = leaf_id
	await session.commit()
	return thread


async def create_message(
	thread_id: TypeID,
	message_in: MessageCreate,
	session: AsyncSession,
) -> Message:
	thread = await _load_thread(thread_id, session)
	data = message_in.model_dump(by_alias=True, exclude={"type"})
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
