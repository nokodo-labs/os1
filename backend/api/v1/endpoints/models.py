"""Model endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.core.database import get_db
from api.models.model import Model
from api.models.provider import Provider
from api.schemas.model import Model as ModelSchema
from api.schemas.model import ModelCreate


router = APIRouter(prefix="/models", tags=["models"])


async def _get_model(model_id: str, db: AsyncSession) -> Model:
	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await db.execute(stmt)
	model = result.scalars().one_or_none()
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)
	return model


async def _ensure_provider(provider_id: str, db: AsyncSession) -> None:
	provider = await db.get(Provider, provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)


@router.post("", response_model=ModelSchema, status_code=status.HTTP_201_CREATED)
async def create_model(
	model_in: ModelCreate,
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Register a model for a provider."""
	await _ensure_provider(model_in.provider_id, db)
	model = Model(**model_in.model_dump(by_alias=True))
	db.add(model)
	await db.commit()
	return await _get_model(model.id, db)


@router.get("", response_model=list[ModelSchema])
async def list_models(
	provider_id: str | None = None,
	db: AsyncSession = Depends(get_db),
) -> list[Model]:
	"""List models with optional provider filter."""
	stmt = (
		select(Model)
		.options(selectinload(Model.provider))
		.order_by(Model.created_at.desc())
	)

	if provider_id:
		stmt = stmt.where(Model.provider_id == provider_id)

	result = await db.execute(stmt)
	return list(result.scalars().all())


@router.get("/{model_id}", response_model=ModelSchema)
async def get_model(
	model_id: str,
	db: AsyncSession = Depends(get_db),
) -> Model:
	"""Fetch a single model."""
	return await _get_model(model_id, db)
