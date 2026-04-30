"""Memory routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.access_rule import AccessRule
from api.models.memory import Memory
from api.permissions import ResourceType
from api.schemas.access_rule import (
	AccessRuleCreate,
	AccessRuleResponse,
)
from api.schemas.memory import Memory as MemorySchema
from api.schemas.memory import MemoryCreate, MemorySortBy, MemoryUpdate
from api.schemas.search import CursorPage, SearchMode, SearchParams, SearchResultItem
from api.schemas.sorting import SortDir
from api.v1.service import access_rules as access_rules_service
from api.v1.service import memories as memory_service
from api.v1.service.auth import Principal, get_current_principal
from api.v1.service.authorization import require_admin
from api.v1.service.events import SessionId
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("/search", response_model=CursorPage[SearchResultItem])
async def search_memories(
	q: str = Query(min_length=1, max_length=500),
	limit: int = Query(default=10, ge=1, le=50),
	cursor: str | None = Query(default=None),
	mode: SearchMode = Query(default=SearchMode.FULL),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> CursorPage[SearchResultItem]:
	"""hybrid search across memories with cursor pagination.

	memories are only searchable via this dedicated endpoint and are NOT
	included in the global /search results.
	"""
	return await memory_service.search_memories(
		q,
		db,
		principal=principal,
		limit=limit,
		cursor=cursor,
		search_params=SearchParams(mode=mode),
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
	user_id: TypeID,
	skip: int = 0,
	limit: int = 50,
	sort_by: MemorySortBy = "updated_at",
	sort_dir: SortDir = "desc",
	search: str | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[MemorySchema]:
	"""list memories for a user."""
	items = await memory_service.list_memories(
		db,
		principal=principal,
		user_id=user_id,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		search=search,
	)
	return [MemorySchema.model_validate(m) for m in items]


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


# ---- access rules ----


@router.get("/{memory_id}/access-rules", response_model=list[AccessRuleResponse])
async def list_memory_access_rules(
	memory_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""list access rules for a memory."""
	return await access_rules_service.list_access_rules(
		ResourceType.MEMORY, memory_id, db, principal=principal
	)


@router.put("/{memory_id}/access-rules", response_model=list[AccessRuleResponse])
async def set_memory_access_rules(
	memory_id: TypeID,
	rules: list[AccessRuleCreate],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[AccessRule]:
	"""replace access rules for a memory."""
	return await access_rules_service.set_access_rules(
		ResourceType.MEMORY,
		memory_id,
		rules,
		db,
		principal=principal,
	)
