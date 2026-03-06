"""Model routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.model import Model
from api.schemas.model import Model as ModelSchema
from api.schemas.model import ModelCreate, ModelUpdate
from api.v1.service import models as model_service
from api.v1.service.auth import Principal, get_current_principal, require_admin


router = APIRouter(
	prefix="/models",
	tags=["models"],
	dependencies=[Depends(require_admin)],
)


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
	model_in: ModelCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Register a model for a provider."""
	return await model_service.create_model(model_in, db, principal=principal)


@router.get("", response_model=list[ModelSchema])
async def list_models(
	provider_id: str | None = None,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Model]:
	"""List models with optional provider filter."""
	return await model_service.list_models(
		db,
		provider_id=provider_id,
		principal=principal,
	)


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
	model_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Fetch a single model."""
	return await model_service.get_model(model_id, db, principal=principal)


@router.patch("/{model_id}", response_model=ModelSchema)
async def update_model(
	model_id: str,
	model_in: ModelUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Update a model."""
	return await model_service.update_model(
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
	await model_service.delete_model(model_id, db, principal=principal)
