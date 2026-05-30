"""service layer for plugin operations."""

from __future__ import annotations

from typing import Literal, overload

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from api.models.plugin import Plugin
from api.permissions import ActionPermission
from api.schemas.plugin import (
	PluginCreate,
	PluginInfo,
	PluginListFilters,
	PluginTypeStr,
	PluginUpdate,
)
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.chat.filters import (
	FILTER_REGISTRY,
)
from api.v1.service.chat.filters import (
	get_registered_names as get_filter_names,
)
from api.v1.service.chat.hooks import (
	HOOK_REGISTRY,
)
from api.v1.service.chat.hooks import (
	get_registered_names as get_hook_names,
)
from api.v1.service.chat.tools.external import (
	get_external_tool_plugin,
	list_external_tool_plugins,
)
from api.v1.service.chat.tools.registry import (
	TOOL_REGISTRY,
)
from api.v1.service.chat.tools.registry import (
	get_registered_names as get_tool_names,
)
from nokodo_ai.utils.typeid import TypeID


PluginTypeFilter = Literal["tool", "filter", "hook"] | None


# internal helpers


def _build_native_info(
	plugin_id: str,
	obj: object,
	plugin_type: PluginTypeStr,
) -> PluginInfo:
	"""build a PluginInfo from a native registry entry."""
	name: str = getattr(obj, "name", plugin_id)
	description: str = getattr(obj, "description", "") or ""
	if not description:
		doc = getattr(obj, "__doc__", None)
		if doc:
			description = doc.strip().split("\n")[0]
		else:
			description = f"{obj.__class__.__name__} {plugin_type}"
	return PluginInfo(
		id=plugin_id,
		name=name,
		description=description,
		type=plugin_type,
		source="native",
	)


def _list_native(plugin_type: PluginTypeFilter = None) -> list[PluginInfo]:
	"""list native (built-in) plugins, optionally filtered by type."""
	plugins: list[PluginInfo] = []
	if plugin_type is None or plugin_type == "tool":
		for tid, tool in TOOL_REGISTRY.items():
			plugins.append(_build_native_info(tid, tool, "tool"))
	if plugin_type is None or plugin_type == "filter":
		for fid, fobj in FILTER_REGISTRY.items():
			plugins.append(_build_native_info(fid, fobj, "filter"))
	if plugin_type is None or plugin_type == "hook":
		for hid, hobj in HOOK_REGISTRY.items():
			plugins.append(_build_native_info(hid, hobj, "hook"))
	return plugins


def _get_native(plugin_id: str) -> PluginInfo | None:
	"""look up a single native plugin by id."""
	if plugin_id in TOOL_REGISTRY:
		return _build_native_info(plugin_id, TOOL_REGISTRY[plugin_id], "tool")
	if plugin_id in FILTER_REGISTRY:
		return _build_native_info(plugin_id, FILTER_REGISTRY[plugin_id], "filter")
	if plugin_id in HOOK_REGISTRY:
		return _build_native_info(plugin_id, HOOK_REGISTRY[plugin_id], "hook")
	return None


def _is_native_name(name: str) -> bool:
	"""check if a name collides with any native plugin name."""
	return (
		name in get_tool_names()
		or name in get_filter_names()
		or name in get_hook_names()
	)


async def _get_db_plugin(plugin_id: TypeID, session: AsyncSession) -> Plugin:
	plugin = await session.get(Plugin, plugin_id)
	if not plugin:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="plugin not found",
		)
	return plugin


def _db_plugin_to_info(plugin: Plugin) -> PluginInfo:
	"""convert a db Plugin ORM object to a PluginInfo response."""
	return PluginInfo(
		id=str(plugin.id),
		name=plugin.name,
		description=plugin.description or "",
		type=plugin.type.value,
		source="custom",
	)


def _apply_plugin_filters(stmt: Select, filters: PluginListFilters) -> Select:
	"""apply plugin filters to a DB query."""
	if filters.plugin_type is not None:
		stmt = stmt.where(Plugin.type == filters.plugin_type)
	return stmt


def _apply_plugin_catalog_filters(
	plugins: list[PluginInfo],
	filters: PluginListFilters,
) -> list[PluginInfo]:
	"""apply plugin filters to in-memory catalog items."""
	return [
		plugin
		for plugin in plugins
		if (filters.source is None or plugin.source == filters.source)
		and (filters.plugin_type is None or plugin.type == filters.plugin_type)
	]


async def _ensure_name_available(
	name: str,
	session: AsyncSession,
	exclude_id: TypeID | None = None,
) -> None:
	if _is_native_name(name):
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="plugin name conflicts with a native plugin",
		)
	stmt = select(Plugin.id).where(Plugin.name == name)
	if exclude_id is not None:
		stmt = stmt.where(Plugin.id != exclude_id)
	if (await session.execute(stmt)).scalar_one_or_none() is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="plugin name already exists",
		)


# public API


async def create_plugin(
	plugin_in: PluginCreate,
	session: AsyncSession,
	principal: Principal,
) -> Plugin:
	require_permission(principal, "plugins:manage")
	await _ensure_name_available(plugin_in.name, session)

	plugin = Plugin(
		name=plugin_in.name,
		description=plugin_in.description,
		type=plugin_in.type,
		author=plugin_in.author,
		version=plugin_in.version,
		source_code=plugin_in.source_code,
		metadata_=plugin_in.metadata,
	)

	session.add(plugin)
	await session.commit()
	await session.refresh(plugin)
	return plugin


@overload
async def list_plugins(
	session: AsyncSession,
	principal: Principal,
	include_native: Literal[False] = ...,
	filters: PluginListFilters | None = ...,
	skip: int = ...,
	limit: int = ...,
) -> list[Plugin]: ...


@overload
async def list_plugins(
	session: AsyncSession,
	principal: Principal,
	include_native: Literal[True],
	filters: PluginListFilters | None = ...,
	skip: int = ...,
	limit: int = ...,
) -> list[PluginInfo]: ...


async def list_plugins(
	session: AsyncSession,
	principal: Principal,
	include_native: bool = False,
	filters: PluginListFilters | None = None,
	skip: int = 0,
	limit: int = 50,
) -> list[Plugin] | list[PluginInfo]:
	"""list plugins.

	when include_native is False, returns only database Plugin ORM objects.
	when include_native is True, returns PluginInfo catalog items from all sources.
	"""
	plugin_filters = filters or PluginListFilters()
	can_read_full_catalog = principal.has_permission(ActionPermission.PLUGINS_READ)
	can_read_user_mcp = principal.has_permission(ActionPermission.USER_MCP_MANAGE)
	if not can_read_full_catalog and not can_read_user_mcp:
		require_permission(principal, ActionPermission.PLUGINS_READ)
	if not can_read_full_catalog:
		if not include_native:
			return []
		if plugin_filters.plugin_type not in (None, "tool"):
			return []
		if plugin_filters.source not in (None, "external"):
			return []
		plugins = await list_external_tool_plugins(session, principal, "tool")
		plugins = _apply_plugin_catalog_filters(plugins, plugin_filters)
		plugins.sort(key=lambda p: p.name)
		return plugins[skip : skip + limit]

	if not include_native:
		if plugin_filters.source not in (None, "custom"):
			return []
		stmt = _apply_plugin_filters(
			select(Plugin).order_by(Plugin.created_at.desc()), plugin_filters
		)
		result = await session.execute(stmt.offset(skip).limit(limit))
		return list(result.scalars().all())

	# Catalog mode: native + external runtime + database as PluginInfo.
	plugins: list[PluginInfo] = []
	if plugin_filters.source in (None, "native"):
		plugins.extend(_list_native())
	if plugin_filters.source in (None, "external"):
		plugins.extend(await list_external_tool_plugins(session, principal, None))

	if plugin_filters.source in (None, "custom"):
		stmt = _apply_plugin_filters(
			select(Plugin).order_by(Plugin.created_at.desc()), plugin_filters
		)
		result = await session.execute(stmt)

		for db_plugin in result.scalars().all():
			plugins.append(_db_plugin_to_info(db_plugin))

	plugins = _apply_plugin_catalog_filters(plugins, plugin_filters)
	plugins.sort(key=lambda p: p.name)
	return plugins[skip : skip + limit]


@overload
async def get_plugin(
	plugin_id: TypeID,
	session: AsyncSession,
	principal: Principal,
	include_native: Literal[False] = ...,
) -> Plugin: ...


@overload
async def get_plugin(
	plugin_id: TypeID | str,
	session: AsyncSession,
	principal: Principal,
	include_native: Literal[True],
) -> PluginInfo: ...


async def get_plugin(
	plugin_id: TypeID | str,
	session: AsyncSession,
	principal: Principal,
	include_native: bool = False,
) -> Plugin | PluginInfo:
	"""get a single plugin.

	when include_native is True, checks native registry first and returns
	PluginInfo. falls back to the database and wraps the result as PluginInfo.
	when include_native is False, looks up only database plugins and returns
	the Plugin ORM object.
	"""
	can_read_full_catalog = principal.has_permission(ActionPermission.PLUGINS_READ)
	can_read_user_mcp = principal.has_permission(ActionPermission.USER_MCP_MANAGE)
	if not can_read_full_catalog and not can_read_user_mcp:
		require_permission(principal, ActionPermission.PLUGINS_READ)

	if include_native:
		if not can_read_full_catalog:
			external_plugin = await get_external_tool_plugin(
				str(plugin_id), session, principal
			)
			if external_plugin is not None:
				return external_plugin
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="plugin not found",
			)
		native = _get_native(str(plugin_id))
		if native:
			return native
		external_plugin = await get_external_tool_plugin(
			str(plugin_id), session, principal
		)
		if external_plugin is not None:
			return external_plugin
		db_plugin = await _get_db_plugin(TypeID(plugin_id), session)
		return _db_plugin_to_info(db_plugin)

	return await _get_db_plugin(TypeID(plugin_id), session)


async def update_plugin(
	plugin_id: TypeID,
	plugin_in: PluginUpdate,
	session: AsyncSession,
	principal: Principal,
) -> Plugin:
	require_permission(principal, "plugins:manage")
	plugin = await _get_db_plugin(plugin_id, session)

	update_data = plugin_in.model_dump(exclude_unset=True, by_alias=True)

	if "name" in plugin_in.model_fields_set:
		name = plugin_in.name
		if not isinstance(name, str):
			raise ValueError("invalid plugin name")
		await _ensure_name_available(
			name,
			session,
			exclude_id=plugin_id,
		)

	for field, value in update_data.items():
		setattr(plugin, field, value)

	await session.commit()
	await session.refresh(plugin)
	return plugin


async def delete_plugin(
	plugin_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	require_permission(principal, "plugins:manage")
	plugin = await _get_db_plugin(plugin_id, session)
	await session.delete(plugin)
	await session.commit()
