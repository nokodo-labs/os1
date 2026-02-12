"""Plugins router (admin-only).

This exposes CRUD for persisted plugins (tools, filters, hooks),
plus endpoints to list all available plugins including native ones.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.plugin import Plugin
from api.schemas.plugin import Plugin as PluginSchema
from api.schemas.plugin import PluginCreate, PluginInfo, PluginUpdate
from api.v1.service import plugins as plugin_service
from api.v1.service.auth import Principal, get_current_principal
from nokodo_ai.utils.typeid import TypeID


router = APIRouter(
	prefix="/plugins",
	tags=["plugins"],
)


PluginTypeFilter = Literal["tool", "filter", "hook"] | None


@router.get("/available", response_model=list[PluginInfo])
async def list_available_plugins(
	plugin_type: PluginTypeFilter = Query(default=None),
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[PluginInfo]:
	"""list all available plugins (native and user-defined).

	native plugins are built into the system and cannot be modified.
	use the plugin_type query parameter to filter by type.
	"""
	return await plugin_service.list_plugins(
		db, principal=principal, include_native=True, plugin_type=plugin_type
	)


@router.get("/available/{plugin_id}", response_model=PluginInfo)
async def get_available_plugin(
	plugin_id: str,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> PluginInfo:
	"""get details about a specific available plugin (native or user-defined)."""
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


@router.get("", response_model=list[PluginSchema])
async def list_plugins(
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> list[Plugin]:
	"""list all plugin records."""
	return await plugin_service.list_plugins(db, principal=principal)


@router.get("/{plugin_id}", response_model=PluginSchema)
async def get_plugin(
	plugin_id: TypeID,
	principal: Principal = Depends(get_current_principal),
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""fetch a plugin record by id."""
	return await plugin_service.get_plugin(plugin_id, db, principal=principal)


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
