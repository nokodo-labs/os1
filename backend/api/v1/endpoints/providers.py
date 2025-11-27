"""Provider endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.provider import Provider
from api.schemas.provider import (
	Provider as ProviderSchema,
)
from api.schemas.provider import (
	ProviderCreate,
	ProviderUpdate,
)


router = APIRouter(prefix="/providers", tags=["providers"])


async def _get_provider(provider_id: str, db: AsyncSession) -> Provider:
	provider = await db.get(Provider, provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)
	return provider


@router.post("", response_model=ProviderSchema, status_code=status.HTTP_201_CREATED)
async def create_provider(
	provider_in: ProviderCreate,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Register a provider."""
	provider = Provider(**provider_in.model_dump(by_alias=True))
	db.add(provider)
	await db.commit()
	await db.refresh(provider)
	return provider


@router.get("", response_model=list[ProviderSchema])
async def list_providers(
	db: AsyncSession = Depends(get_db),
) -> list[Provider]:
	"""List configured providers."""
	result = await db.execute(select(Provider).order_by(Provider.name))
	return list(result.scalars().all())


@router.get("/{provider_id}", response_model=ProviderSchema)
async def get_provider(
	provider_id: str,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Fetch a provider."""
	return await _get_provider(provider_id, db)


@router.patch("/{provider_id}", response_model=ProviderSchema)
async def update_provider(
	provider_id: str,
	provider_in: ProviderUpdate,
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Update provider fields."""
	provider = await _get_provider(provider_id, db)
	updates = provider_in.model_dump(exclude_unset=True, by_alias=True)

	for field, value in updates.items():
		setattr(provider, field, value)

	await db.commit()
	await db.refresh(provider)
	return provider
