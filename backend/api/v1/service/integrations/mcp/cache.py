"""Redis cache helpers for MCP DB snapshot projections."""

from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import UnboundExecutionError
from sqlalchemy.ext.asyncio import AsyncSession

from api.boot_settings import boot_settings
from api.redis import cache
from api.schemas.mcp import MCPDiscoveredCapabilities, MCPDiscoveredTool
from api.schemas.plugin import PluginInfo
from api.settings import settings


class CachedMCPPromptRef(BaseModel):
	"""DB-derived MCP prompt reference safe to cache in Redis."""

	server_id: str
	name: str
	command: str


class CachedMCPServerTools(BaseModel):
	"""DB-derived MCP server tool snapshot safe to cache in Redis."""

	name: str
	tools: list[MCPDiscoveredTool]


async def invalidate_mcp_cache(
	session: AsyncSession,
	server_id: object | None = None,
) -> None:
	"""invalidate cached MCP DB snapshot projections affected by a change."""
	namespace = _cache_namespace(session)
	await _invalidate_tag(f"mcp:{namespace}:global")
	if server_id is not None:
		await _invalidate_tag(f"mcp:{namespace}:server:{server_id}")


async def get_cached_mcp_plugins(session: AsyncSession) -> list[PluginInfo] | None:
	"""return cached MCP plugin projections, or None when unavailable."""
	namespace = _cache_namespace(session)
	key = f"mcp:{namespace}:plugins:tool"
	value = await _get_cache_value(key)
	if not isinstance(value, list):
		return None
	try:
		return [PluginInfo.model_validate(item) for item in value]
	except ValidationError:
		await _delete_cache_key(key)
		return None


async def set_cached_mcp_plugins(
	session: AsyncSession,
	plugins: list[PluginInfo],
) -> None:
	"""cache MCP plugin projections derived from the database snapshot."""
	namespace = _cache_namespace(session)
	await _set_cache_value(
		f"mcp:{namespace}:plugins:tool",
		[plugin.model_dump(mode="json") for plugin in plugins],
		ttl=settings.cache.mcp_snapshot_ttl_seconds,
		tags=[f"mcp:{namespace}:global"],
	)


async def get_cached_mcp_capabilities(
	session: AsyncSession,
	server_id: str,
) -> MCPDiscoveredCapabilities | None:
	"""return cached discovered capabilities for one MCP server."""
	namespace = _cache_namespace(session)
	key = f"mcp:{namespace}:capabilities:{server_id}"
	value = await _get_cache_value(key)
	if not isinstance(value, dict):
		return None
	try:
		return MCPDiscoveredCapabilities.model_validate(value)
	except ValidationError:
		await _delete_cache_key(key)
		return None


async def set_cached_mcp_capabilities(
	session: AsyncSession,
	server_id: str,
	capabilities: MCPDiscoveredCapabilities,
) -> None:
	"""cache discovered capabilities derived from one MCP server row."""
	namespace = _cache_namespace(session)
	await _set_cache_value(
		f"mcp:{namespace}:capabilities:{server_id}",
		capabilities.model_dump(mode="json"),
		ttl=settings.cache.mcp_snapshot_ttl_seconds,
		tags=[f"mcp:{namespace}:global", f"mcp:{namespace}:server:{server_id}"],
	)


async def get_cached_mcp_server_tools(
	session: AsyncSession,
	server_id: str,
) -> CachedMCPServerTools | None:
	"""return cached enabled tool snapshots for one MCP server."""
	namespace = _cache_namespace(session)
	key = f"mcp:{namespace}:server-tools:{server_id}"
	value = await _get_cache_value(key)
	if not isinstance(value, dict):
		return None
	try:
		return CachedMCPServerTools.model_validate(value)
	except ValidationError:
		await _delete_cache_key(key)
		return None


async def set_cached_mcp_server_tools(
	session: AsyncSession,
	server_id: str,
	snapshot: CachedMCPServerTools,
) -> None:
	"""cache enabled tool snapshots for one MCP server."""
	namespace = _cache_namespace(session)
	await _set_cache_value(
		f"mcp:{namespace}:server-tools:{server_id}",
		snapshot.model_dump(mode="json"),
		ttl=settings.cache.mcp_snapshot_ttl_seconds,
		tags=[f"mcp:{namespace}:global", f"mcp:{namespace}:server:{server_id}"],
	)


async def get_cached_mcp_prompt_refs(
	session: AsyncSession,
) -> dict[str, CachedMCPPromptRef] | None:
	"""return cached no-argument MCP prompt references keyed by command."""
	namespace = _cache_namespace(session)
	key = f"mcp:{namespace}:prompt-refs"
	value = await _get_cache_value(key)
	if not isinstance(value, dict):
		return None
	try:
		return {
			str(command): CachedMCPPromptRef.model_validate(ref)
			for command, ref in value.items()
		}
	except ValidationError:
		await _delete_cache_key(key)
		return None


async def set_cached_mcp_prompt_refs(
	session: AsyncSession,
	refs: dict[str, CachedMCPPromptRef],
) -> None:
	"""cache no-argument MCP prompt references derived from DB snapshots."""
	namespace = _cache_namespace(session)
	await _set_cache_value(
		f"mcp:{namespace}:prompt-refs",
		{command: ref.model_dump(mode="json") for command, ref in refs.items()},
		ttl=settings.cache.mcp_snapshot_ttl_seconds,
		tags=[f"mcp:{namespace}:global"],
	)


def _cache_namespace(session: AsyncSession) -> str:
	"""derive a stable Redis namespace from the active database binding."""
	try:
		bind = session.get_bind()
	except (AttributeError, UnboundExecutionError):
		seed = f"{boot_settings.DATABASE_URL}:unbound:{id(session)}"
		return sha256(seed.encode()).hexdigest()[:16]
	url = getattr(bind, "url", None)
	if url is None:
		seed = boot_settings.DATABASE_URL
	else:
		seed = url.render_as_string(hide_password=True)
	return sha256(seed.encode()).hexdigest()[:16]


async def _get_cache_value(key: str) -> object | None:
	"""read an MCP cache value and fail open if Redis is not connected yet."""
	try:
		return await cache.get(key)
	except RuntimeError:
		return None


async def _set_cache_value(
	key: str,
	value: object,
	ttl: int,
	tags: list[str],
) -> None:
	"""write an MCP cache value and skip caching if Redis is unavailable."""
	try:
		await cache.set(key, value, ttl=ttl, tags=tags)
	except RuntimeError:
		return


async def _delete_cache_key(key: str) -> None:
	"""delete a corrupt MCP cache entry and ignore unavailable Redis."""
	try:
		await cache.delete(key)
	except RuntimeError:
		return


async def _invalidate_tag(tag: str) -> None:
	"""invalidate an MCP cache tag and ignore unavailable Redis."""
	try:
		await cache.invalidate_tag(tag)
	except RuntimeError:
		return
