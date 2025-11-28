"""Model routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.model import Model
from api.schemas.model import Model as ModelSchema
from api.schemas.model import ModelCreate
from api.v1.service import models as model_service


router = APIRouter(prefix="/models", tags=["models"])


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
	model_in: ModelCreate,
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Register a model for a provider."""
	return await model_service.create_model(model_in, db)


@router.get("", response_model=list[ModelSchema])
async def list_models(
	provider_id: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[Model]:
	"""List models with optional provider filter."""
	return await model_service.list_models(db, provider_id=provider_id)


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
	model_id: str,
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Fetch a single model."""
	return await model_service.get_model(model_id, db)
