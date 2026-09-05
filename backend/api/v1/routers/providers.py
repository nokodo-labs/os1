"""Provider routers."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.provider import Provider
from api.schemas.provider import Provider as ProviderSchema
from api.schemas.provider import ProviderCreate, ProviderUpdate
from api.v1.service.authentication import Principal, get_current_principal
from api.v1.service.providers import (
	create_provider as create_provider_service,
)
from api.v1.service.providers import (
	get_provider as get_provider_service,
)
from api.v1.service.providers import (
	list_providers as list_providers_service,
)
from api.v1.service.providers import (
	update_provider as update_provider_service,
)


router = APIRouter(
	prefix="/providers",
	tags=["providers"],
)


@router.post("", response_model=ProviderSchema, status_code=status.HTTP_201_CREATED)
async def create_provider(
	provider_in: ProviderCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Register a provider."""
	return await create_provider_service(provider_in, db, principal=principal)


@router.get("", response_model=list[ProviderSchema])
async def list_providers(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Provider]:
	"""List configured providers."""
	return await list_providers_service(db, principal=principal)


@router.get("/{provider_id}", response_model=ProviderSchema)
async def get_provider(
	provider_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Fetch a provider."""
	return await get_provider_service(provider_id, db, principal=principal)


@router.patch("/{provider_id}", response_model=ProviderSchema)
async def update_provider(
	provider_id: str,
	provider_in: ProviderUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Provider:
	"""Update provider fields."""
	return await update_provider_service(
		provider_id,
		provider_in,
		db,
		principal=principal,
	)
