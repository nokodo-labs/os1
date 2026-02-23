"""prompt routers."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.prompt import Prompt
from api.schemas.prompt import Prompt as PromptSchema
from api.schemas.prompt import PromptCreate, PromptUpdate
from api.schemas.sorting import CommonSortBy, SortDir
from api.v1.service import prompts as prompt_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(
	prefix="/prompts",
	tags=["prompts"],
)


PromptSortBy = Literal["command"]


@router.post("", response_model=PromptSchema, status_code=status.HTTP_201_CREATED)
async def create_prompt(
	prompt_in: PromptCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Prompt:
	"""create a prompt."""
	return await prompt_service.create_prompt(prompt_in, db, principal=principal)


@router.get("", response_model=list[PromptSchema])
async def list_prompts(
	skip: int = 0,
	limit: int = 50,
	sort_by: CommonSortBy | PromptSortBy = "command",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Prompt]:
	"""list prompts."""
	return await prompt_service.list_prompts(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
	)


@router.get("/{prompt_id}", response_model=PromptSchema)
async def get_prompt(
	prompt_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Prompt:
	"""fetch a prompt."""
	return await prompt_service.get_prompt(prompt_id, db, principal=principal)


@router.patch("/{prompt_id}", response_model=PromptSchema)
async def update_prompt(
	prompt_id: TypeID,
	prompt_in: PromptUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Prompt:
	"""update a prompt."""
	return await prompt_service.update_prompt(
		prompt_id, prompt_in, db, principal=principal
	)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
	prompt_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a prompt."""
	await prompt_service.delete_prompt(prompt_id, db, principal=principal)
