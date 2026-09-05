"""prompt routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.prompt import Prompt
from api.schemas.prompt import Prompt as PromptSchema
from api.schemas.prompt import (
	PromptCreate,
	PromptListFilters,
	PromptSortBy,
	PromptUpdate,
)
from api.schemas.sorting import SortDir
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.prompts import (
	count_prompts as count_prompts_service,
)
from api.v1.service.prompts import (
	create_prompt as create_prompt_service,
)
from api.v1.service.prompts import (
	delete_prompt as delete_prompt_service,
)
from api.v1.service.prompts import (
	get_prompt as get_prompt_service,
)
from api.v1.service.prompts import (
	list_prompts as list_prompts_service,
)
from api.v1.service.prompts import (
	update_prompt as update_prompt_service,
)
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(
	prefix="/prompts",
	tags=["prompts"],
)


@router.post("", response_model=PromptSchema, status_code=status.HTTP_201_CREATED)
async def create_prompt(
	prompt_in: PromptCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Prompt:
	"""create a prompt."""
	return await create_prompt_service(prompt_in, db, principal=principal)


@router.get("", response_model=list[PromptSchema])
async def list_prompts(
	filters: Annotated[PromptListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	sort_by: PromptSortBy = "command",
	sort_dir: SortDir = "asc",
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[PromptSchema]:
	"""list prompts."""
	return await list_prompts_service(
		db,
		principal=principal,
		skip=skip,
		limit=limit,
		sort_by=sort_by,
		sort_dir=sort_dir,
		filters=filters,
	)


@router.get("/count", response_model=int)
async def count_prompts(
	filters: Annotated[PromptListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> int:
	"""count prompts matching the list filters."""
	return await count_prompts_service(
		db,
		principal=principal,
		filters=filters,
	)


@router.get("/{prompt_id}", response_model=PromptSchema)
async def get_prompt(
	prompt_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> PromptSchema:
	"""fetch a prompt."""
	return await get_prompt_service(prompt_id, db, principal=principal)


@router.patch("/{prompt_id}", response_model=PromptSchema)
async def update_prompt(
	prompt_id: TypeID,
	prompt_in: PromptUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Prompt:
	"""update a prompt."""
	return await update_prompt_service(prompt_id, prompt_in, db, principal=principal)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
	prompt_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a prompt."""
	await delete_prompt_service(prompt_id, db, principal=principal)
