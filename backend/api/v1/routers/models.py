"""Model routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.model import Model
from api.schemas.model import Model as ModelSchema
from api.schemas.model import ModelCreate, ModelListFilters, ModelUpdate
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.models import (
	create_model as create_model_service,
)
from api.v1.service.models import (
	delete_model as delete_model_service,
)
from api.v1.service.models import (
	get_model as get_model_service,
)
from api.v1.service.models import (
	list_models as list_models_service,
)
from api.v1.service.models import (
	update_model as update_model_service,
)


router = APIRouter(
	prefix="/models",
	tags=["models"],
)


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
	model_in: ModelCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Register a model for a provider."""
	return await create_model_service(model_in, db, principal=principal)


@router.get("", response_model=list[ModelSchema])
async def list_models(
	filters: Annotated[ModelListFilters, Depends()],
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Model]:
	"""List models with optional provider filter."""
	return await list_models_service(
		db,
		filters=filters,
		principal=principal,
	)


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
	model_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Fetch a single model."""
	return await get_model_service(model_id, db, principal=principal)


@router.patch("/{model_id}", response_model=ModelSchema)
async def update_model(
	model_id: str,
	model_in: ModelUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Update a model."""
	return await update_model_service(
		model_id,
		model_in,
		db,
		principal=principal,
	)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(
	model_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""Delete a model."""
	await delete_model_service(model_id, db, principal=principal)
