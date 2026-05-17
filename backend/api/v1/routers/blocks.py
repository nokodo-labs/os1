"""user block routers - nested under /users/{user_id}."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.block import Block
from api.schemas.block import BlockCreate, BlockDetail
from api.v1.service import blocks as blocks_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(prefix="/{user_id}/blocks", tags=["blocks"])


@router.get("", response_model=list[BlockDetail])
async def list_blocks(
	user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Block]:
	"""list users blocked by the path user."""
	return await blocks_service.list_blocks(
		db,
		principal=principal,
		subject_user_id=user_id,
	)


@router.post("", response_model=BlockDetail, status_code=status.HTTP_201_CREATED)
async def block_user(
	user_id: TypeID,
	body: BlockCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Block:
	"""block another user for the path user."""
	return await blocks_service.block_user(
		db,
		principal=principal,
		subject_user_id=user_id,
		blocked_user_id=body.blocked_id,
	)


@router.delete("/{blocked_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock_user(
	user_id: TypeID,
	blocked_user_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""unblock a user for the path user."""
	await blocks_service.unblock_user(
		db,
		principal=principal,
		subject_user_id=user_id,
		blocked_user_id=blocked_user_id,
	)
