"""Memory routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.memory import Memory
from api.permissions import ResourceType
from api.schemas.memory import Memory as MemorySchema
from api.schemas.memory import (
	MemoryCreate,
	MemoryListFilters,
	MemorySearchFilters,
	MemorySortBy,
	MemoryUpdate,
)
from api.schemas.search import Page, SearchMode, SearchParams
from api.schemas.sorting import SortDir
from api.v1.routers.resource_access import create_resource_access_router
from api.v1.service import memories as memory_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/memories", tags=["memories"])
router.include_router(create_resource_access_router(ResourceType.MEMORY, "memory_id"))


@router.get("/search", response_model=Page[MemorySchema])
async def search_memories(
	filters: Annotated[MemorySearchFilters, Depends()],
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	offset: int = Query(default=0, ge=0),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Page[MemorySchema]:
	"""hybrid search across memories, returning relevance-ordered memories.

	memories are only searchable via this dedicated endpoint and are NOT
	included in the global /search results.
	"""
	scored = await memory_service.search_memories(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=[MemorySchema.model_validate(hit.item) for hit in scored[:limit]],
		has_more=len(scored) > limit,
	)


@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
async def create_memory(
	memory_in: MemoryCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Memory:
	"""capture a new memory."""
	return await memory_service.create_memory(
		memory_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.get("", response_model=list[MemorySchema])
async def list_memories(
	filters: Annotated[MemoryListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: MemorySortBy = "updated_at",
	sort_dir: SortDir = "desc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MemorySchema]:
	"""list memories for a user."""
	items = await memory_service.list_memories(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)
	return [MemorySchema.model_validate(m) for m in items]


@router.get("/count", response_model=int)
async def count_memories(
	filters: Annotated[MemoryListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count memories matching the list filters."""
	return await memory_service.count_memories(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/{memory_id}", response_model=MemorySchema)
async def get_memory(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Memory:
	"""fetch a single memory."""
	return await memory_service.get_memory(memory_id, db, principal=principal)


@router.put("/{memory_id}", response_model=MemorySchema)
async def update_memory(
	memory_id: TypeID,
	memory_in: MemoryUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> Memory:
	"""update a memory."""
	return await memory_service.update_memory(
		memory_id,
		memory_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a memory."""
	await memory_service.delete_memory(
		memory_id,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_memories(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete all memories for the current user."""
	await memory_service.delete_all_memories(
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)


@router.post("/revectorize")
async def revectorize_memories(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
	"""vectorize all memories. admin only."""
	require_admin(principal)
	count = await memory_service.vectorize_all_memories(db)
	return {"vectorized": count}
