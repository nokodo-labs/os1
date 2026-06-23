"""Plugins router (admin-only).

This exposes CRUD for persisted plugins (tools, filters, hooks),
plus endpoints to list all available plugins including native ones.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.plugin import Plugin
from api.schemas.plugin import Plugin as PluginSchema
from api.schemas.plugin import PluginCreate, PluginInfo, PluginListFilters, PluginUpdate
from api.v1.service import plugins as plugin_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(
	prefix="/plugins",
	tags=["plugins"],
)


@router.get("", response_model=list[PluginInfo])
async def list_plugins(
	filters: Annotated[PluginListFilters, Depends()],
	skip: int = 0,
	limit: int = 50,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[PluginInfo]:
	"""list plugin catalog items."""
	return await plugin_service.list_plugins(
		db,
		principal=principal,
		include_native=True,
		filters=filters,
		skip=skip,
		limit=limit,
	)


@router.get("/{plugin_id}", response_model=PluginInfo)
async def get_plugin(
	plugin_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> PluginInfo:
	"""get details about a plugin catalog item."""
	return await plugin_service.get_plugin(
		plugin_id, db, principal=principal, include_native=True
	)


@router.post("", response_model=PluginSchema, status_code=status.HTTP_201_CREATED)
async def create_plugin(
	plugin_in: PluginCreate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""create a plugin record."""
	return await plugin_service.create_plugin(plugin_in, db, principal=principal)


@router.patch("/{plugin_id}", response_model=PluginSchema)
async def update_plugin(
	plugin_id: TypeID,
	plugin_in: PluginUpdate,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""update plugin fields."""
	return await plugin_service.update_plugin(
		plugin_id, plugin_in, db, principal=principal
	)


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
	plugin_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> None:
	"""delete a plugin record."""
	await plugin_service.delete_plugin(plugin_id, db, principal=principal)
