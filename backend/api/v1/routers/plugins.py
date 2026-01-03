"""Plugins router (admin-only).

This exposes CRUD for persisted plugins (tools, filters, hooks),
plus endpoints to list all available plugins including native ones.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.database import get_db
from api.models.plugin import Plugin
from api.schemas.plugin import Plugin as PluginSchema
from api.schemas.plugin import PluginCreate, PluginInfo, PluginUpdate
from api.v1.service import plugins as plugin_service
from api.v1.service.auth import require_admin


router = APIRouter(
	prefix="/plugins",
	tags=["plugins"],
	dependencies=[Depends(require_admin)],
)


PluginTypeFilter = Literal["tool", "filter", "hook"] | None


@router.get("/available", response_model=list[PluginInfo])
async def list_available_plugins(
	plugin_type: PluginTypeFilter = Query(default=None),
	db: AsyncSession = Depends(get_db),
) -> list[PluginInfo]:
	"""list all available plugins (native and user-defined).

	native plugins are built into the system and cannot be modified.
	use the plugin_type query parameter to filter by type.
	"""
	return await plugin_service.list_available_plugins(db, plugin_type)


@router.get("/available/{plugin_id}", response_model=PluginInfo)
async def get_available_plugin(
	plugin_id: str,
	db: AsyncSession = Depends(get_db),
) -> PluginInfo:
	"""get details about a specific available plugin (native or user-defined)."""
	# try native first
	native = plugin_service.get_native_plugin(plugin_id)
	if native:
		return native

	# try database
	try:
		db_plugin = await plugin_service.get_plugin(plugin_id, db)
		return PluginInfo(
			id=str(db_plugin.id),
			name=db_plugin.name,
			description=db_plugin.description or "",
			type=db_plugin.type.value,
			is_native=False,
		)
	except HTTPException:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="plugin not found",
		)


@router.post("", response_model=PluginSchema, status_code=status.HTTP_201_CREATED)
async def create_plugin(
	plugin_in: PluginCreate,
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""Create a plugin record."""
	return await plugin_service.create_plugin(plugin_in, db)


@router.get("", response_model=list[PluginSchema])
async def list_plugins(
	db: AsyncSession = Depends(get_db),
) -> list[Plugin]:
	"""List all plugin records."""
	return await plugin_service.list_plugins(db)


@router.get("/{plugin_id}", response_model=PluginSchema)
async def get_plugin(
	plugin_id: str,
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""Fetch a plugin record by id."""
	return await plugin_service.get_plugin(plugin_id, db)


@router.patch("/{plugin_id}", response_model=PluginSchema)
async def update_plugin(
	plugin_id: str,
	plugin_in: PluginUpdate,
	db: AsyncSession = Depends(get_db),
) -> Plugin:
	"""Update plugin fields."""
	return await plugin_service.update_plugin(plugin_id, plugin_in, db)


@router.delete("/{plugin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plugin(
	plugin_id: str,
	db: AsyncSession = Depends(get_db),
) -> None:
	"""Delete a plugin record."""
	await plugin_service.delete_plugin(plugin_id, db)
