"""Service helpers for providers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings
from api.models.provider import Provider
from api.schemas.provider import ProviderCreate, ProviderUpdate
from nokodo_ai.utils.security import encrypt_string


async def _get_provider(provider_id: str, session: AsyncSession) -> Provider:
	provider = await session.get(Provider, provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)
	return provider


async def create_provider(
	provider_in: ProviderCreate,
	session: AsyncSession,
) -> Provider:
	data = provider_in.model_dump(by_alias=True, exclude={"api_key"})
	if provider_in.api_key:
		data["encrypted_api_key"] = encrypt_string(
			provider_in.api_key, settings.SECRET_KEY
		)

	provider = Provider(**data)
	session.add(provider)
	await session.commit()
	await session.refresh(provider)
	return provider


async def list_providers(session: AsyncSession) -> list[Provider]:
	result = await session.execute(select(Provider).order_by(Provider.name))
	return list(result.scalars().all())


async def get_provider(provider_id: str, session: AsyncSession) -> Provider:
	return await _get_provider(provider_id, session)


async def update_provider(
	provider_id: str,
	provider_in: ProviderUpdate,
	session: AsyncSession,
) -> Provider:
	provider = await _get_provider(provider_id, session)
	updates = provider_in.model_dump(
		exclude_unset=True, by_alias=True, exclude={"api_key"}
	)

	if provider_in.api_key:
		updates["encrypted_api_key"] = encrypt_string(
			provider_in.api_key, settings.SECRET_KEY
		)

	for field, value in updates.items():
		setattr(provider, field, value)

	session.add(provider)
	await session.commit()
	await session.refresh(provider)
	return provider
