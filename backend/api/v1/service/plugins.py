"""Service layer for plugin operations (admin-only)."""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.plugin import Plugin
from api.schemas.plugin import PluginCreate, PluginInfo, PluginUpdate
from api.v1.service.chat.filters import FILTER_REGISTRY
from api.v1.service.chat.hooks import HOOK_REGISTRY
from api.v1.service.chat.tools import TOOL_REGISTRY


PluginTypeFilter = Literal["tool", "filter", "hook"] | None


async def _get_plugin(plugin_id: str, session: AsyncSession) -> Plugin:
	plugin = await session.get(Plugin, plugin_id)
	if not plugin:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="plugin not found",
		)
	return plugin


async def _ensure_name_available(
	name: str,
	session: AsyncSession,
	*,
	exclude_id: str | None = None,
) -> None:
	stmt = select(Plugin.id).where(Plugin.name == name)
	if exclude_id is not None:
		stmt = stmt.where(Plugin.id != exclude_id)
	if (await session.execute(stmt)).scalar_one_or_none() is not None:
		raise HTTPException(
			status_code=status.HTTP_409_CONFLICT,
			detail="plugin name already exists",
		)


async def create_plugin(plugin_in: PluginCreate, session: AsyncSession) -> Plugin:
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
	return await _get_plugin(str(plugin.id), session)


async def list_plugins(session: AsyncSession) -> list[Plugin]:
	stmt = select(Plugin).order_by(Plugin.created_at.desc())
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def get_plugin(plugin_id: str, session: AsyncSession) -> Plugin:
	return await _get_plugin(plugin_id, session)


async def update_plugin(
	plugin_id: str,
	plugin_in: PluginUpdate,
	session: AsyncSession,
) -> Plugin:
	plugin = await _get_plugin(plugin_id, session)

	update_data = plugin_in.model_dump(exclude_unset=True)
	if "metadata" in update_data:
		update_data["metadata_"] = update_data.pop("metadata")

	if plugin_in.name is not None:
		await _ensure_name_available(
			plugin_in.name,
			session,
			exclude_id=str(plugin.id),
		)

	for field, value in update_data.items():
		setattr(plugin, field, value)

	session.add(plugin)
	await session.commit()
	# ensure server-side updated columns (e.g., updated_at) are loaded
	await session.refresh(plugin)
	return await _get_plugin(str(plugin.id), session)


async def delete_plugin(plugin_id: str, session: AsyncSession) -> None:
	plugin = await _get_plugin(plugin_id, session)
	await session.delete(plugin)
	await session.commit()


def list_native_plugins(plugin_type: PluginTypeFilter = None) -> list[PluginInfo]:
	"""list all available native (built-in) plugins.

	args:
		plugin_type: optional filter by type ('tool', 'filter', 'hook')

	returns:
		list of native plugins, optionally filtered by type
	"""
	plugins: list[PluginInfo] = []

	# add tools
	if plugin_type is None or plugin_type == "tool":
		for tool_id, tool in TOOL_REGISTRY.items():
			plugins.append(
				PluginInfo(
					id=tool_id,
					name=tool.name,
					description=tool.description,
					type="tool",
					is_native=True,
				)
			)

	# add filters
	if plugin_type is None or plugin_type == "filter":
		for filter_id, filter_instance in FILTER_REGISTRY.items():
			description = filter_instance.description
			if not description:
				if filter_instance.__doc__:
					description = filter_instance.__doc__.strip().split("\n")[0]
				else:
					description = f"{filter_instance.__class__.__name__} filter"

			plugins.append(
				PluginInfo(
					id=filter_id,
					name=filter_instance.name,
					description=description,
					type="filter",
					is_native=True,
				)
			)

	# add hooks
	if plugin_type is None or plugin_type == "hook":
		for hook_id, hook_instance in HOOK_REGISTRY.items():
			description = hook_instance.description
			if not description:
				if hook_instance.__doc__:
					description = hook_instance.__doc__.strip().split("\n")[0]
				else:
					description = f"{hook_instance.__class__.__name__} hook"

			plugins.append(
				PluginInfo(
					id=hook_id,
					name=hook_instance.name,
					description=description,
					type="hook",
					is_native=True,
				)
			)

	return plugins


def get_native_plugin(plugin_id: str) -> PluginInfo | None:
	"""get a single native plugin by id."""
	# check tools
	if plugin_id in TOOL_REGISTRY:
		tool = TOOL_REGISTRY[plugin_id]
		return PluginInfo(
			id=plugin_id,
			name=tool.name,
			description=tool.description,
			type="tool",
			is_native=True,
		)

	# check filters
	if plugin_id in FILTER_REGISTRY:
		filter_instance = FILTER_REGISTRY[plugin_id]
		description = filter_instance.description
		if not description:
			if filter_instance.__doc__:
				description = filter_instance.__doc__.strip().split("\n")[0]
			else:
				description = f"{filter_instance.__class__.__name__} filter"

		return PluginInfo(
			id=plugin_id,
			name=filter_instance.name,
			description=description,
			type="filter",
			is_native=True,
		)

	# check hooks
	if plugin_id in HOOK_REGISTRY:
		hook_instance = HOOK_REGISTRY[plugin_id]
		description = hook_instance.description
		if not description:
			if hook_instance.__doc__:
				description = hook_instance.__doc__.strip().split("\n")[0]
			else:
				description = f"{hook_instance.__class__.__name__} hook"

		return PluginInfo(
			id=plugin_id,
			name=hook_instance.name,
			description=description,
			type="hook",
			is_native=True,
		)

	return None


async def list_available_plugins(
	session: AsyncSession,
	plugin_type: PluginTypeFilter = None,
) -> list[PluginInfo]:
	"""list all available plugins (both native and user-defined).

	args:
		session: database session
		plugin_type: optional filter by type ('tool', 'filter', 'hook')

	returns:
		combined list of native plugins + database plugins
	"""
	# get native plugins
	plugins = list_native_plugins(plugin_type)

	# get database plugins
	stmt = select(Plugin).order_by(Plugin.created_at.desc())
	if plugin_type is not None:
		stmt = stmt.where(Plugin.type == plugin_type)
	result = await session.execute(stmt)

	for db_plugin in result.scalars().all():
		plugins.append(
			PluginInfo(
				id=str(db_plugin.id),
				name=db_plugin.name,
				description=db_plugin.description or "",
				type=db_plugin.type.value,
				is_native=False,
			)
		)

	return plugins
