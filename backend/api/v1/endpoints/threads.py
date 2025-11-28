"""Thread and message endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_db
from api.models.agent import Agent
from api.models.message import (
	AssistantMessage,
	Message,
	MessageType,
	SystemMessage,
	ToolMessage,
	UserMessage,
)
from api.models.thread import Thread
from api.models.user import User
from api.schemas.message import Message as MessageSchema
from api.schemas.message import MessageCreate
from api.schemas.thread import Thread as ThreadSchema
from api.schemas.thread import ThreadCreate, ThreadUpdate


router = APIRouter(prefix="/threads", tags=["threads"])


async def _load_thread(
	thread_id: str,
	db: AsyncSession,
) -> Thread:
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.user_participants),
			selectinload(Thread.agent_participants).selectinload(Agent.model),
		)
		.where(Thread.id == thread_id)
	)
	result = await db.execute(stmt)
	thread = result.scalars().unique().one_or_none()

	if not thread:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Thread not found",
		)

	return thread


async def _ensure_user(user_id: int, db: AsyncSession) -> None:
	user = await db.get(User, user_id)
	if not user:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="User not found",
		)


@router.post("", response_model=ThreadSchema, status_code=status.HTTP_201_CREATED)
async def create_thread(
	thread_in: ThreadCreate,
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Create a new thread."""
	await _ensure_user(thread_in.user_id, db)
	thread = Thread(**thread_in.model_dump(by_alias=True))
	db.add(thread)
	await db.commit()
	return await _load_thread(thread.id, db)


@router.get("", response_model=list[ThreadSchema])
async def list_threads(
	user_id: int | None = None,
	skip: int = 0,
	limit: int = 20,
	db: AsyncSession = Depends(get_db),
) -> list[Thread]:
	"""List threads optionally filtered by owner."""
	stmt = (
		select(Thread)
		.options(
			selectinload(Thread.messages),
			selectinload(Thread.owner),
			selectinload(Thread.user_participants),
			selectinload(Thread.agent_participants).selectinload(Agent.model),
		)
		.order_by(Thread.last_activity_at.desc())
	)

	if user_id:
		stmt = stmt.where(Thread.user_id == user_id)

	result = await db.execute(stmt.offset(skip).limit(limit))
	return list(result.scalars().unique().all())


@router.get("/{thread_id}", response_model=ThreadSchema)
async def get_thread(
	thread_id: str,
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Fetch a single thread with messages."""
	return await _load_thread(thread_id, db)


@router.patch("/{thread_id}", response_model=ThreadSchema)
async def update_thread(
	thread_id: str,
	thread_in: ThreadUpdate,
	db: AsyncSession = Depends(get_db),
) -> Thread:
	"""Update thread metadata."""
	thread = await _load_thread(thread_id, db)
	update_data = thread_in.model_dump(exclude_unset=True, by_alias=True)
	if "user_id" in update_data and update_data["user_id"] is not None:
		await _ensure_user(update_data["user_id"], db)

	for field, value in update_data.items():
		setattr(thread, field, value)

	await db.commit()
	return await _load_thread(thread_id, db)


@router.get("/{thread_id}/messages", response_model=list[MessageSchema])
async def list_messages(
	thread_id: str,
	skip: int = 0,
	limit: int = 100,
	db: AsyncSession = Depends(get_db),
) -> list[Message]:
	"""List messages within a thread."""
	await _load_thread(thread_id, db)
	stmt = (
		select(Message)
		.where(Message.thread_id == thread_id)
		.order_by(Message.created_at)
		.offset(skip)
		.limit(limit)
	)
	result = await db.execute(stmt)
	return list(result.scalars().all())


@router.post(
	"/{thread_id}/messages",
	response_model=MessageSchema,
	status_code=status.HTTP_201_CREATED,
)
async def create_message(
	thread_id: str,
	message_in: MessageCreate,
	db: AsyncSession = Depends(get_db),
) -> Message:
	"""Append a message to a thread."""
	thread = await _load_thread(thread_id, db)

	data = message_in.model_dump(by_alias=True)
	msg_type = data.pop("type", MessageType.USER)

	if msg_type == MessageType.USER:
		message = UserMessage(thread_id=thread_id, **data)
	elif msg_type == MessageType.ASSISTANT:
		message = AssistantMessage(thread_id=thread_id, **data)
	elif msg_type == MessageType.TOOL:
		message = ToolMessage(thread_id=thread_id, **data)
	elif msg_type == MessageType.SYSTEM:
		message = SystemMessage(thread_id=thread_id, **data)
	else:
		# Fallback to UserMessage if unknown, or raise error
		message = UserMessage(thread_id=thread_id, **data)

	thread.last_activity_at = datetime.now(tz=UTC)
	db.add(message)
	await db.commit()
	await db.refresh(message)
	return message
