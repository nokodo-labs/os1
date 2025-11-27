"""Memory endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_db
from api.models.memory import Memory
from api.models.thread import Thread
from api.schemas.memory import Memory as MemorySchema
from api.schemas.memory import MemoryCreate


router = APIRouter(prefix="/memories", tags=["memories"])


async def _get_memory(memory_id: str, db: AsyncSession) -> Memory:
	stmt = (
		select(Memory)
		.options(
			selectinload(Memory.owner),
			selectinload(Memory.thread).selectinload(Thread.messages),
		)
		.where(Memory.id == memory_id)
	)
	result = await db.execute(stmt)
	memory = result.scalars().one_or_none()
	if not memory:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Memory not found",
		)
	return memory


@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
async def create_memory(
	memory_in: MemoryCreate,
	db: AsyncSession = Depends(get_db),
) -> Memory:
	"""Capture a new memory."""
	memory = Memory(**memory_in.model_dump(by_alias=True))
	db.add(memory)
	await db.commit()
	return await _get_memory(memory.id, db)


@router.get("", response_model=list[MemorySchema])
async def list_memories(
	user_id: int,
	skip: int = 0,
	limit: int = 50,
	db: AsyncSession = Depends(get_db),
) -> list[Memory]:
	"""List memories for a user."""
	stmt = (
		select(Memory)
		.options(
			selectinload(Memory.owner),
			selectinload(Memory.thread).selectinload(Thread.messages),
		)
		.where(Memory.user_id == user_id)
		.order_by(Memory.updated_at.desc())
		.offset(skip)
		.limit(limit)
	)
	result = await db.execute(stmt)
	return list(result.scalars().all())


@router.get("/{memory_id}", response_model=MemorySchema)
async def get_memory(
	memory_id: str,
	db: AsyncSession = Depends(get_db),
) -> Memory:
	"""Fetch a single memory."""
	return await _get_memory(memory_id, db)
