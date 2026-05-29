"""external chat tool source registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.plugin import PluginInfo, PluginTypeFilter
from nokodo_ai.tool import Tool


if TYPE_CHECKING:
	from api.v1.service.chat.context import AppContext

type ResolveExternalTools = Callable[
	[list[str], AppContext],
	Awaitable[list[Tool[AppContext]]],
]
type ListExternalToolPlugins = Callable[
	[AsyncSession, PluginTypeFilter],
	Awaitable[list[PluginInfo]],
]
type GetExternalToolPlugin = Callable[
	[str, AsyncSession],
	Awaitable[PluginInfo | None],
]


@dataclass(frozen=True)
class ExternalToolSource:
	"""registered provider for runtime tools outside the native registry."""

	name: str
	prefix: str
	resolve_tools: ResolveExternalTools
	list_plugins: ListExternalToolPlugins
	get_plugin: GetExternalToolPlugin


_SOURCES_BY_NAME: dict[str, ExternalToolSource] = {}


def register_external_tool_source(source: ExternalToolSource) -> None:
	"""register an external tool source with a unique tool id prefix."""
	_validate_source_shape(source)
	existing = _SOURCES_BY_NAME.get(source.name)
	if existing is not None:
		if existing == source:
			return
		raise ValueError(f"external tool source already registered: {source.name}")
	for registered in _SOURCES_BY_NAME.values():
		if _prefixes_overlap(source.prefix, registered.prefix):
			raise ValueError(
				"external tool source prefix conflicts with "
				f"{registered.name}: {source.prefix}"
			)
	_SOURCES_BY_NAME[source.name] = source


def has_external_tool_source(tool_id: str) -> bool:
	"""return whether a tool id belongs to an external source prefix."""
	return any(tool_id.startswith(source.prefix) for source in _sources())


async def resolve_external_tools(
	tool_ids: list[str],
	app_context: AppContext,
) -> list[Tool[AppContext]]:
	"""resolve external tool ids through their registered source."""
	tools: list[Tool[AppContext]] = []
	for source in _sources():
		source_tool_ids = [
			tool_id for tool_id in tool_ids if tool_id.startswith(source.prefix)
		]
		if not source_tool_ids:
			continue
		tools.extend(await source.resolve_tools(source_tool_ids, app_context))
	return tools


async def list_external_tool_plugins(
	session: AsyncSession,
	plugin_type: PluginTypeFilter = None,
) -> list[PluginInfo]:
	"""list plugin metadata from registered external tool sources."""
	plugins: list[PluginInfo] = []
	seen: set[str] = set()
	for source in _sources():
		source_plugins = await source.list_plugins(session, plugin_type)
		_validate_source_plugins(source, source_plugins)
		for plugin in source_plugins:
			if plugin.id in seen:
				raise ValueError(f"duplicate external tool plugin id: {plugin.id}")
			seen.add(plugin.id)
			plugins.append(plugin)
	return plugins


async def get_external_tool_plugin(
	plugin_id: str,
	session: AsyncSession,
) -> PluginInfo | None:
	"""look up one external tool plugin through its source prefix."""
	for source in _sources():
		if not plugin_id.startswith(source.prefix):
			continue
		plugin = await source.get_plugin(plugin_id, session)
		if plugin is not None:
			_validate_source_plugins(source, [plugin])
			return plugin
	return None


def _sources() -> tuple[ExternalToolSource, ...]:
	"""return the currently wired external tool sources."""
	return tuple(_SOURCES_BY_NAME.values())


def _validate_source_shape(source: ExternalToolSource) -> None:
	"""validate one external tool source before registration."""
	if not source.name.strip():
		raise ValueError("external tool source name is required")
	if not source.prefix.strip():
		raise ValueError("external tool source prefix is required")
	if source.prefix != source.prefix.strip():
		raise ValueError("external tool source prefix cannot include edge spaces")


def _validate_source_plugins(
	source: ExternalToolSource,
	plugins: list[PluginInfo],
) -> None:
	"""ensure every exposed plugin belongs to its tool source prefix."""
	for plugin in plugins:
		if not plugin.id.startswith(source.prefix):
			raise ValueError(
				"external tool source emitted plugin id outside prefix "
				f"{source.name}: {plugin.id}"
			)


def _prefixes_overlap(left: str, right: str) -> bool:
	"""return whether two tool source prefixes would route ambiguously."""
	return left.startswith(right) or right.startswith(left)
