"""Service layer for memory operations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.memory import Memory
from api.schemas.memory import MemoryCreate


async def _get_memory(memory_id: str, session: AsyncSession) -> Memory:
	stmt = (
		select(Memory).options(selectinload(Memory.owner)).where(Memory.id == memory_id)
	)
	result = await session.execute(stmt)
	memory = result.scalars().one_or_none()
	if not memory:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Memory not found",
		)
	return memory


async def create_memory(memory_in: MemoryCreate, session: AsyncSession) -> Memory:
	memory = Memory(**memory_in.model_dump(by_alias=True))
	session.add(memory)
	await session.commit()
	return await _get_memory(memory.id, session)


async def list_memories(
	session: AsyncSession,
	user_id: int,
	skip: int = 0,
	limit: int = 50,
) -> list[Memory]:
	stmt = (
		select(Memory)
		.options(selectinload(Memory.owner))
		.where(Memory.user_id == user_id)
		.order_by(Memory.updated_at.desc())
		.offset(skip)
		.limit(limit)
	)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_memory(memory_id: str, session: AsyncSession) -> Memory:
	return await _get_memory(memory_id, session)
