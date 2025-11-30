"""Service helpers for threads and messages."""

from __future__ import annotations

from datetime import UTC, datetime

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


async def _load_thread(thread_id: str, session: AsyncSession) -> Thread:
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


async def _ensure_user(user_id: int, session: AsyncSession) -> None:
	user = await session.get(User, user_id)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)


async def _load_projects(
	project_ids: list[str],
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
	return await _load_thread(thread.id, session)


async def list_threads(
	session: AsyncSession,
	owner_id: int | None = None,
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


async def get_thread(thread_id: str, session: AsyncSession) -> Thread:
	return await _load_thread(thread_id, session)


async def update_thread(
	thread_id: str,
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
	thread_id: str,
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


async def create_message(
	thread_id: str,
	message_in: MessageCreate,
	session: AsyncSession,
) -> Message:
	thread = await _load_thread(thread_id, session)
	data = message_in.model_dump(by_alias=True, exclude={"type"})

	match message_in.type:
		case MessageType.USER:
			message = UserMessage(thread_id=thread_id, **data)
		case MessageType.ASSISTANT:
			message = AssistantMessage(thread_id=thread_id, **data)
		case MessageType.TOOL:
			message = ToolMessage(thread_id=thread_id, **data)
		case MessageType.SYSTEM:
			message = SystemMessage(thread_id=thread_id, **data)
		case _:
			message = UserMessage(thread_id=thread_id, **data)

	thread.last_activity_at = datetime.now(tz=UTC)
	session.add(message)
	await session.commit()
	await session.refresh(message)
	return message
