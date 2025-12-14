"""Service layer for provider models."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.models.model import Model
from api.models.provider import Provider
from api.schemas.model import ModelCreate, ModelUpdate


async def _ensure_provider(provider_id: str, session: AsyncSession) -> None:
	provider = await session.get(Provider, provider_id)
	if not provider:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Provider not found",
		)


async def _get_model(model_id: str, session: AsyncSession) -> Model:
	stmt = (
		select(Model).options(selectinload(Model.provider)).where(Model.id == model_id)
	)
	result = await session.execute(stmt)
	model = result.scalars().one_or_none()
	if not model:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Model not found",
		)
	return model


async def create_model(model_in: ModelCreate, session: AsyncSession) -> Model:
	await _ensure_provider(model_in.provider_id, session)
	model = Model(**model_in.model_dump(by_alias=True))
	session.add(model)
	await session.commit()
	return await _get_model(model.id, session)


async def list_models(
	session: AsyncSession,
	provider_id: str | None = None,
) -> list[Model]:
	stmt = (
		select(Model)
		.options(selectinload(Model.provider))
		.order_by(Model.created_at.desc())
	)

	if provider_id:
		stmt = stmt.where(Model.provider_id == provider_id)

	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_model(model_id: str, session: AsyncSession) -> Model:
	return await _get_model(model_id, session)


async def update_model(
	model_id: str, model_in: ModelUpdate, session: AsyncSession
) -> Model:
	model = await _get_model(model_id, session)

	update_data = model_in.model_dump(exclude_unset=True)
	for field, value in update_data.items():
		setattr(model, field, value)

	await session.commit()
	return await _get_model(model_id, session)


async def delete_model(model_id: str, session: AsyncSession) -> None:
	model = await _get_model(model_id, session)
	await session.delete(model)
	await session.commit()
