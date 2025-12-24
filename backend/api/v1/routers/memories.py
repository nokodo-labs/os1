"""Memory routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.memory import Memory
from api.schemas.memory import Memory as MemorySchema
from api.schemas.memory import MemoryCreate
from api.v1.service import memories as memory_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/memories", tags=["memories"])


@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
async def create_memory(
	memory_in: MemoryCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Memory:
	"""Capture a new memory."""
	return await memory_service.create_memory(memory_in, db, principal=principal)


@router.get("", response_model=list[MemorySchema])
async def list_memories(
	user_id: TypeID,
	skip: int = 0,
	limit: int = 50,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Memory]:
	"""List memories for a user."""
	return await memory_service.list_memories(
		db,
		principal=principal,
		user_id=user_id,
		skip=skip,
		limit=limit,
	)


@router.get("/{memory_id}", response_model=MemorySchema)
async def get_memory(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Memory:
	"""Fetch a single memory."""
	return await memory_service.get_memory(memory_id, db, principal=principal)
