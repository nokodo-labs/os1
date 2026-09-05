"""Memory routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
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
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.events import SessionId
from api.v1.service.memories import (
	count_memories as count_memories_service,
)
from api.v1.service.memories import (
	create_memory as create_memory_service,
)
from api.v1.service.memories import (
	delete_all_memories as delete_all_memories_service,
)
from api.v1.service.memories import (
	delete_memory as delete_memory_service,
)
from api.v1.service.memories import (
	get_memory as get_memory_service,
)
from api.v1.service.memories import (
	list_memories as list_memories_service,
)
from api.v1.service.memories import (
	memory_payloads,
	vectorize_memories,
)
from api.v1.service.memories import (
	search_memories as search_memories_service,
)
from api.v1.service.memories import (
	update_memory as update_memory_service,
)
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
	scored = await search_memories_service(
		q,
		db,
		principal=principal,
		limit=limit + 1,
		offset=offset,
		search_params=SearchParams(mode=mode),
		filters=filters,
	)
	return Page(
		items=memory_payloads([hit.item for hit in scored[:limit]], principal),
		has_more=len(scored) > limit,
	)


@router.post("", response_model=MemorySchema, status_code=status.HTTP_201_CREATED)
async def create_memory(
	memory_in: MemoryCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> MemorySchema:
	"""capture a new memory."""
	memory = await create_memory_service(
		memory_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return memory_payloads([memory], principal)[0]


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
	items = await list_memories_service(
		db,
		principal=principal,
		filters=filters,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)
	return memory_payloads(items, principal)


@router.get("/count", response_model=int)
async def count_memories(
	filters: Annotated[MemoryListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count memories matching the list filters."""
	return await count_memories_service(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/{memory_id}", response_model=MemorySchema)
async def get_memory(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> MemorySchema:
	"""fetch a single memory."""
	memory = await get_memory_service(memory_id, db, principal=principal)
	return memory_payloads([memory], principal)[0]


@router.put("/{memory_id}", response_model=MemorySchema)
async def update_memory(
	memory_id: TypeID,
	memory_in: MemoryUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> MemorySchema:
	"""update a memory."""
	memory = await update_memory_service(
		memory_id,
		memory_in,
		db,
		principal=principal,
		origin_session_id=x_session_id,
	)
	return memory_payloads([memory], principal)[0]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
	x_session_id: SessionId = None,
) -> None:
	"""delete a memory."""
	await delete_memory_service(
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
	await delete_all_memories_service(
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
	count = await vectorize_memories(db)
	return {"vectorized": count}
