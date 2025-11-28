"""Provider routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.provider import Provider
from api.schemas.provider import Provider as ProviderSchema
from api.schemas.provider import ProviderCreate, ProviderUpdate
from api.v1.service import providers as provider_service


router = APIRouter(prefix="/providers", tags=["providers"])


@router.post("", response_model=ProviderSchema, status_code=status.HTTP_201_CREATED)
async def create_provider(
	provider_in: ProviderCreate,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Register a provider."""
	return await provider_service.create_provider(provider_in, db)


@router.get("", response_model=list[ProviderSchema])
async def list_providers(
	db: AsyncSession = Depends(get_db),
) -> list[Provider]:
	"""List configured providers."""
	return await provider_service.list_providers(db)


@router.get("/{provider_id}", response_model=ProviderSchema)
async def get_provider(
	provider_id: str,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Fetch a provider."""
	return await provider_service.get_provider(provider_id, db)


@router.patch("/{provider_id}", response_model=ProviderSchema)
async def update_provider(
	provider_id: str,
	provider_in: ProviderUpdate,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Update provider fields."""
	return await provider_service.update_provider(provider_id, provider_in, db)
