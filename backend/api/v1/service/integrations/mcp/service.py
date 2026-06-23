"""service layer for MCP server operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_attribute

from api.mcp import MCPClient, MCPClientConfig, MCPDependencyError, MCPError
from api.mcp.types import MCPCapabilitySnapshot, MCPToolCallResult
from api.models.mcp import (
	MCPAuthType,
	MCPServer,
	MCPServerScope,
	MCPServerStatus,
	MCPTransport,
)
from api.permissions import ActionPermission
from api.schemas.mcp import (
	MCPCapabilityType,
	MCPCapabilityUpdate,
	MCPDiscoveredCapabilities,
	MCPDiscoveredPrompt,
	MCPDiscoveredResource,
	MCPDiscoveredTool,
	MCPDiscoveryResult,
	MCPPromptArgument,
	MCPServerCreate,
	MCPServerUpdate,
	MCPSurfaceConfig,
)
from api.schemas.mcp import MCPServer as MCPServerSchema
from api.schemas.plugin import PluginInfo, PluginTypeFilter
from api.settings import settings
from api.v1.service.auth import Principal
from api.v1.service.authorization import require_permission
from api.v1.service.integrations.mcp.cache import (
	get_cached_mcp_capabilities,
	get_cached_mcp_plugins,
	invalidate_mcp_cache,
	set_cached_mcp_capabilities,
	set_cached_mcp_plugins,
)
from api.v1.service.integrations.mcp.ids import (
	mcp_server_tools_plugin_id,
	mcp_tool_plugin_id,
)
from api.v1.service.integrations.mcp.normalization import (
	normalized_input_schema,
	normalized_mcp_prompt_command,
	normalized_mcp_tool_name,
	schema_hash,
)
from nokodo_ai.types.json import JSONObject, JSONValue
from nokodo_ai.utils.security import decrypt_string_with_fallback, encrypt_string
from nokodo_ai.utils.tokens import estimate_tokens
from nokodo_ai.utils.typeid import TypeID, new_typeid


type DiscoveryError = MCPDependencyError | MCPError | OSError | ValueError


MCP_TOOL_TYPEID_PREFIX = "mcptool"
MCP_RESOURCE_TYPEID_PREFIX = "mcpres"
MCP_PROMPT_TYPEID_PREFIX = "mcpprompt"


def _require_read(principal: Principal) -> None:
	_require_integration_enabled()
	if _can_manage_global_mcp(principal):
		return
	if _can_manage_user_mcp(principal):
		return
	require_permission(principal, ActionPermission.MCP_MANAGE)


def _require_manage(principal: Principal) -> None:
	_require_integration_enabled()
	require_permission(principal, ActionPermission.MCP_MANAGE)


def _require_integration_enabled() -> None:
	if not settings.integrations.mcp.enabled:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="MCP integration is disabled",
		)


def _can_manage_global_mcp(principal: Principal) -> bool:
	return principal.has_permission(ActionPermission.MCP_MANAGE)


def _can_manage_user_mcp(principal: Principal) -> bool:
	return principal.has_permission(ActionPermission.USER_MCP_MANAGE)


def _require_user_mcp_manage(principal: Principal) -> None:
	_require_integration_enabled()
	require_permission(principal, ActionPermission.USER_MCP_MANAGE)


async def list_servers(
	session: AsyncSession,
	principal: Principal,
) -> list[MCPServer]:
	"""list MCP servers visible to the principal."""
	_require_read(principal)
	stmt = select(MCPServer).order_by(MCPServer.created_at.desc())
	if not _can_manage_global_mcp(principal):
		stmt = stmt.where(
			MCPServer.scope == MCPServerScope.USER,
			MCPServer.owner_user_id == str(principal.user_id),
		)
	result = await session.execute(stmt)
	return list(result.scalars().all())


async def list_user_servers(
	session: AsyncSession,
	principal: Principal,
) -> list[MCPServer]:
	"""list the current user's MCP servers."""
	_require_user_mcp_manage(principal)
	result = await session.execute(
		select(MCPServer)
		.where(
			MCPServer.scope == MCPServerScope.USER,
			MCPServer.owner_user_id == str(principal.user_id),
		)
		.order_by(MCPServer.created_at.desc())
	)
	return list(result.scalars().all())


async def get_server(
	server_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> MCPServer:
	"""get an MCP server visible to the principal."""
	_require_read(principal)
	server = await _get_server(server_id, session)
	_require_server_read(server, principal)
	return server


async def create_server(
	server_in: MCPServerCreate,
	session: AsyncSession,
	principal: Principal,
) -> MCPServer:
	"""create an MCP server."""
	if server_in.scope is MCPServerScope.GLOBAL:
		_require_manage(principal)
		_validate_server_payload(server_in)
	elif server_in.scope is MCPServerScope.USER:
		_require_user_mcp_manage(principal)
		_validate_user_server_payload(server_in)
		await _ensure_user_server_count_allowed(session, principal)
	else:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="unsupported MCP server scope",
		)
	data = server_in.model_dump(
		mode="json",
		exclude={"access_token"},
		by_alias=True,
	)
	if server_in.scope is MCPServerScope.USER:
		data["owner_user_id"] = str(principal.user_id)
		data["capabilities"] = _user_mcp_surface().model_dump(mode="json")
	server = MCPServer(**data)
	if server_in.access_token:
		server.encrypted_access_token = _encrypt_access_token(server_in.access_token)
	session.add(server)
	await session.flush()
	await session.refresh(server)
	await invalidate_mcp_cache(session, server.id)
	return server


async def update_server(
	server_id: TypeID,
	server_in: MCPServerUpdate,
	session: AsyncSession,
	principal: Principal,
) -> MCPServer:
	"""update an MCP server."""
	_require_integration_enabled()
	server = await _get_server(server_id, session)
	_require_server_manage(server, principal)
	_validate_server_update(server, server_in)
	if server.scope is MCPServerScope.USER:
		_validate_user_server_update(server, server_in)
	fields = server_in.model_fields_set
	name_changed = False
	if "name" in fields and isinstance(server_in.name, str):
		name_changed = server.name != server_in.name
		server.name = server_in.name
	if "description" in fields:
		server.description = (
			server_in.description if isinstance(server_in.description, str) else None
		)
	if "transport" in fields and isinstance(server_in.transport, MCPTransport):
		server.transport = server_in.transport
	if "url" in fields:
		server.url = server_in.url if isinstance(server_in.url, str) else None
	if "command" in fields:
		server.command = (
			server_in.command if isinstance(server_in.command, str) else None
		)
	if "args" in fields and isinstance(server_in.args, list):
		set_attribute(server, "args", server_in.args)
	if "env" in fields and isinstance(server_in.env, dict):
		set_attribute(server, "env", server_in.env)
	if "auth_type" in fields and isinstance(server_in.auth_type, MCPAuthType):
		server.auth_type = server_in.auth_type
	if "headers" in fields and isinstance(server_in.headers, dict):
		set_attribute(server, "headers", server_in.headers)
	if "enabled" in fields and isinstance(server_in.enabled, bool):
		server.enabled = server_in.enabled
	if "capabilities" in fields and isinstance(
		server_in.capabilities, MCPSurfaceConfig
	):
		server.capabilities = server_in.capabilities.model_dump(mode="json")
	if "config" in fields and isinstance(server_in.config, dict):
		set_attribute(server, "config", server_in.config)
	if "metadata" in fields and isinstance(server_in.metadata, dict):
		set_attribute(server, "metadata_", server_in.metadata)
	if "access_token" in server_in.model_fields_set:
		server.encrypted_access_token = (
			_encrypt_access_token(server_in.access_token)
			if isinstance(server_in.access_token, str) and server_in.access_token
			else None
		)
	if name_changed:
		_refresh_snapshot_names(server)
	server.status = MCPServerStatus.DISCONNECTED
	server.last_error = None
	session.add(server)
	await session.flush()
	await session.refresh(server)
	await invalidate_mcp_cache(session, server.id)
	return server


async def delete_server(
	server_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> None:
	"""delete an MCP server."""
	_require_integration_enabled()
	server = await _get_server(server_id, session)
	_require_server_manage(server, principal)
	await session.delete(server)
	await session.flush()
	await invalidate_mcp_cache(session, server.id)


async def list_capabilities(
	server_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> MCPDiscoveredCapabilities:
	"""list latest discovered capabilities for an MCP server."""
	_require_read(principal)
	server = await _get_server(server_id, session)
	_require_server_read(server, principal)
	if server.scope is MCPServerScope.GLOBAL:
		cached = await get_cached_mcp_capabilities(session, str(server_id))
		if cached is not None:
			return cached
	capabilities = _capabilities_from_server(server)
	if server.scope is MCPServerScope.GLOBAL:
		await set_cached_mcp_capabilities(session, str(server.id), capabilities)
	return capabilities


async def update_capability(
	server_id: TypeID,
	capability_type: MCPCapabilityType,
	capability_id: TypeID,
	capability_in: MCPCapabilityUpdate,
	session: AsyncSession,
	principal: Principal,
) -> MCPServer:
	"""update a discovered capability snapshot."""
	_require_integration_enabled()
	server = await _get_server(server_id, session)
	_require_server_manage(server, principal)
	capabilities = _capabilities_from_server(server)
	updated = _set_capability_enabled(
		capabilities,
		capability_type,
		capability_id,
		capability_in.enabled,
	)
	if not updated:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="MCP capability not found",
		)
	_store_capabilities(server, capabilities)
	session.add(server)
	await session.flush()
	await session.refresh(server)
	await invalidate_mcp_cache(session, server.id)
	return server


async def discover_server(
	server_id: TypeID,
	session: AsyncSession,
	principal: Principal,
) -> MCPDiscoveryResult:
	"""discover and cache capabilities for an MCP server."""
	_require_integration_enabled()
	server = await _get_server(server_id, session)
	_require_server_manage(server, principal)
	try:
		capabilities = await discover_server_unchecked(server, session)
	except MCPDependencyError, MCPError, OSError, ValueError:
		capabilities = _capabilities_from_server(server)
	return MCPDiscoveryResult(
		server=MCPServerSchema.model_validate(server),
		capabilities=capabilities,
	)


async def discover_server_unchecked(
	server: MCPServer,
	session: AsyncSession,
) -> MCPDiscoveredCapabilities:
	"""discover and cache capabilities for a server without permission checks."""
	try:
		config = client_config(server)
		include_resources = _surface(server).resources
		include_prompts = _surface(server).prompts
		async with MCPClient(config) as client:
			snapshot = await client.discover(
				include_resources=include_resources,
				include_prompts=include_prompts,
			)
		capabilities = _replace_discovered_snapshot(server, snapshot)
		server.status = MCPServerStatus.READY
		server.last_error = None
		server.last_discovered_at = datetime.now(UTC)
		session.add(server)
		await session.flush()
		await session.refresh(server)
		await invalidate_mcp_cache(session, server.id)
		return capabilities
	except (MCPDependencyError, MCPError, OSError, ValueError) as exc:
		server.status = MCPServerStatus.ERROR
		server.last_error = str(exc)
		session.add(server)
		await session.flush()
		await session.refresh(server)
		raise


async def list_available_plugins(
	session: AsyncSession,
	plugin_type: PluginTypeFilter = None,
	principal: Principal | None = None,
) -> list[PluginInfo]:
	"""list MCP tools as available dynamic plugins."""
	if not settings.integrations.mcp.enabled:
		return []
	if plugin_type is not None and plugin_type != "tool":
		return []
	if principal is not None and not principal.has_permission(
		ActionPermission.PLUGINS_READ
	):
		if not _can_manage_user_mcp(principal):
			return []
		return await _list_user_available_plugins(session, principal)
	cached = await get_cached_mcp_plugins(session)
	if cached is not None:
		return await _with_user_available_plugins(cached, session, principal)
	servers = await _list_enabled_global_servers(session)
	plugins: list[PluginInfo] = []
	for server in servers:
		tools = _enabled_tools(server)
		if not tools:
			continue
		plugins.append(
			PluginInfo(
				id=mcp_server_tools_plugin_id(str(server.id)),
				name=f"{server.name} tools",
				description=server.description
				or "all enabled tools from this MCP server",
				type="tool",
				source="external",
			)
		)
		plugins.extend(_tool_plugin_info(server, tool) for tool in tools)
	plugins.sort(key=lambda p: p.name)
	await set_cached_mcp_plugins(session, plugins)
	return await _with_user_available_plugins(plugins, session, principal)


async def get_available_plugin(
	plugin_id: str,
	session: AsyncSession,
	principal: Principal | None = None,
) -> PluginInfo | None:
	"""return MCP plugin metadata for one dynamic plugin id."""
	if not settings.integrations.mcp.enabled:
		return None
	for plugin in await list_available_plugins(session, "tool", principal):
		if plugin.id == plugin_id:
			return plugin
	return None


async def call_tool(
	server_id: str,
	tool_id: str,
	tool_name: str,
	arguments: JSONObject,
	session: AsyncSession,
	principal: Principal | None = None,
) -> MCPToolCallResult:
	"""call a tool on an MCP server."""
	_require_integration_enabled()
	server, tool = await _get_enabled_tool(
		server_id,
		tool_id,
		tool_name,
		session,
		principal,
	)
	async with MCPClient(client_config(server)) as client:
		return await client.call_tool(tool.name, arguments)


async def _get_enabled_tool(
	server_id: str,
	tool_id: str,
	tool_name: str,
	session: AsyncSession,
	principal: Principal | None = None,
) -> tuple[MCPServer, MCPDiscoveredTool]:
	server = await _get_enabled_global_server(server_id, session)
	if server is None and principal is not None:
		server = await _get_enabled_user_server(server_id, session, principal)
	if server is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="MCP tool not found"
		)
	tool = _find_enabled_tool(server, tool_id)
	if tool is None or tool.name != tool_name:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="MCP tool not found"
		)
	return server, tool


async def _get_server(server_id: TypeID, session: AsyncSession) -> MCPServer:
	server = await session.get(MCPServer, server_id)
	if server is None:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
		)
	return server


def _require_server_read(server: MCPServer, principal: Principal) -> None:
	if _can_manage_global_mcp(principal):
		return
	if server.scope is MCPServerScope.USER and server.owner_user_id == str(
		principal.user_id
	):
		_require_user_mcp_manage(principal)
		return
	raise HTTPException(
		status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
	)


def _require_server_manage(server: MCPServer, principal: Principal) -> None:
	_require_server_read(server, principal)
	if server.scope is MCPServerScope.USER and not _can_manage_global_mcp(principal):
		_require_user_mcp_manage(principal)


def _user_mcp_surface() -> MCPSurfaceConfig:
	return MCPSurfaceConfig(tools=True, resources=False, prompts=False, sampling=False)


async def _get_enabled_global_server(
	server_id: str,
	session: AsyncSession,
) -> MCPServer | None:
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.id == server_id,
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
	)
	return result.scalars().one_or_none()


async def _get_enabled_user_server(
	server_id: str,
	session: AsyncSession,
	principal: Principal,
) -> MCPServer | None:
	if not _can_manage_user_mcp(principal):
		return None
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.id == server_id,
			MCPServer.scope == MCPServerScope.USER,
			MCPServer.owner_user_id == str(principal.user_id),
			MCPServer.enabled.is_(True),
		)
	)
	return result.scalars().one_or_none()


async def _list_enabled_global_servers(session: AsyncSession) -> list[MCPServer]:
	result = await session.execute(
		select(MCPServer)
		.where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
		)
		.order_by(MCPServer.name)
	)
	return list(result.scalars().all())


async def _list_enabled_user_servers(
	session: AsyncSession,
	principal: Principal,
) -> list[MCPServer]:
	result = await session.execute(
		select(MCPServer)
		.where(
			MCPServer.scope == MCPServerScope.USER,
			MCPServer.owner_user_id == str(principal.user_id),
			MCPServer.enabled.is_(True),
		)
		.order_by(MCPServer.name)
	)
	return list(result.scalars().all())


async def _list_user_available_plugins(
	session: AsyncSession,
	principal: Principal,
) -> list[PluginInfo]:
	servers = await _list_enabled_user_servers(session, principal)
	plugins: list[PluginInfo] = []
	for server in servers:
		plugins.extend(
			_tool_plugin_info(server, tool) for tool in _enabled_tools(server)
		)
	plugins.sort(key=lambda p: p.name)
	return plugins


async def _with_user_available_plugins(
	plugins: list[PluginInfo],
	session: AsyncSession,
	principal: Principal | None,
) -> list[PluginInfo]:
	if principal is None or not _can_manage_user_mcp(principal):
		return plugins
	combined = [*plugins, *(await _list_user_available_plugins(session, principal))]
	combined.sort(key=lambda p: p.name)
	return combined


async def _ensure_user_server_count_allowed(
	session: AsyncSession,
	principal: Principal,
) -> None:
	max_count = settings.integrations.mcp.user_server_max_count
	count = await session.scalar(
		select(func.count())
		.select_from(MCPServer)
		.where(
			MCPServer.scope == MCPServerScope.USER,
			MCPServer.owner_user_id == str(principal.user_id),
		)
	)
	if (count or 0) >= max_count:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="user-owned MCP server limit reached",
		)


def _capabilities_from_server(server: MCPServer) -> MCPDiscoveredCapabilities:
	return MCPDiscoveredCapabilities(
		tools=_server_tools(server),
		resources=_server_resources(server),
		prompts=_server_prompts(server),
	)


def _enabled_tools(server: MCPServer) -> list[MCPDiscoveredTool]:
	if not _surface(server).tools:
		return []
	return [tool for tool in _server_tools(server) if tool.enabled]


def _find_enabled_tool(
	server: MCPServer,
	tool_id: str,
) -> MCPDiscoveredTool | None:
	for tool in _enabled_tools(server):
		if str(tool.id) == tool_id:
			return tool
	return None


def _set_capability_enabled(
	capabilities: MCPDiscoveredCapabilities,
	capability_type: MCPCapabilityType,
	capability_id: TypeID,
	enabled: bool,
) -> bool:
	if capability_type is MCPCapabilityType.TOOL:
		for tool in capabilities.tools:
			if tool.id == capability_id:
				tool.enabled = enabled
				return True
		return False
	if capability_type is MCPCapabilityType.RESOURCE:
		for resource in capabilities.resources:
			if resource.id == capability_id:
				resource.enabled = enabled
				return True
		return False
	for prompt in capabilities.prompts:
		if prompt.id == capability_id:
			prompt.enabled = enabled
			return True
	return False


def _server_tools(server: MCPServer) -> list[MCPDiscoveredTool]:
	return [
		MCPDiscoveredTool.model_validate(item)
		for item in (server.discovered_tools or [])
	]


def _server_resources(server: MCPServer) -> list[MCPDiscoveredResource]:
	return [
		MCPDiscoveredResource.model_validate(item)
		for item in (server.discovered_resources or [])
	]


def _server_prompts(server: MCPServer) -> list[MCPDiscoveredPrompt]:
	return [
		MCPDiscoveredPrompt.model_validate(item)
		for item in (server.discovered_prompts or [])
	]


def _tool_plugin_info(server: MCPServer, tool: MCPDiscoveredTool) -> PluginInfo:
	return PluginInfo(
		id=mcp_tool_plugin_id(str(server.id), str(tool.id)),
		name=f"{server.name}: {tool.name}",
		description=tool.description or "MCP tool",
		type="tool",
		source="external",
	)


def _replace_discovered_snapshot(
	server: MCPServer,
	snapshot: MCPCapabilitySnapshot,
) -> MCPDiscoveredCapabilities:
	now = datetime.now(UTC)
	old_tools = {tool.name: tool for tool in _server_tools(server)}
	old_resources = {resource.uri: resource for resource in _server_resources(server)}
	old_prompts = {prompt.name: prompt for prompt in _server_prompts(server)}
	tool_ids: set[str] = set()
	resource_ids: set[str] = set()
	prompt_ids: set[str] = set()
	tools: list[MCPDiscoveredTool] = []
	resources: list[MCPDiscoveredResource] = []
	prompts: list[MCPDiscoveredPrompt] = []

	seen_tools: set[str] = set()
	for tool in snapshot.tools:
		_assert_unique_snapshot_key("tool", tool.name, seen_tools)
		old_tool = old_tools.get(tool.name)
		input_schema = normalized_input_schema(tool.input_schema)
		tools.append(
			MCPDiscoveredTool(
				id=_snapshot_id(old_tool, MCP_TOOL_TYPEID_PREFIX, tool_ids),
				name=tool.name,
				normalized_name=normalized_mcp_tool_name(server.name, tool.name),
				description=tool.description,
				input_schema=input_schema,
				output_schema=None,
				enabled=old_tool.enabled if old_tool is not None else True,
				schema_hash=schema_hash(tool.description, input_schema, None),
				last_discovered_at=now,
			)
		)

	snapshot_resources = (
		[] if server.scope is MCPServerScope.USER else snapshot.resources
	)
	snapshot_prompts = [] if server.scope is MCPServerScope.USER else snapshot.prompts

	seen_resources: set[str] = set()
	for resource in snapshot_resources:
		_assert_unique_snapshot_key("resource", resource.uri, seen_resources)
		old_resource = old_resources.get(resource.uri)
		resources.append(
			MCPDiscoveredResource(
				id=_snapshot_id(old_resource, MCP_RESOURCE_TYPEID_PREFIX, resource_ids),
				uri=resource.uri,
				name=resource.name,
				description=resource.description,
				mime_type=resource.mime_type,
				enabled=old_resource.enabled if old_resource is not None else True,
				schema_hash=schema_hash(
					resource.uri,
					resource.name,
					resource.description,
					resource.mime_type,
				),
				last_discovered_at=now,
			)
		)

	seen_prompts: set[str] = set()
	for prompt in snapshot_prompts:
		_assert_unique_snapshot_key("prompt", prompt.name, seen_prompts)
		old_prompt = old_prompts.get(prompt.name)
		prompt_id = _snapshot_id(old_prompt, MCP_PROMPT_TYPEID_PREFIX, prompt_ids)
		arguments = _prompt_arguments(prompt.arguments)
		arguments_json: list[JSONValue] = [argument for argument in prompt.arguments]
		prompts.append(
			MCPDiscoveredPrompt(
				id=prompt_id,
				name=prompt.name,
				command=normalized_mcp_prompt_command(
					str(server.id),
					str(prompt_id),
					prompt.name,
				),
				description=prompt.description,
				arguments=arguments,
				enabled=old_prompt.enabled if old_prompt is not None else True,
				schema_hash=schema_hash(prompt.description, arguments_json),
				last_discovered_at=now,
			)
		)

	capabilities = MCPDiscoveredCapabilities(
		tools=tools,
		resources=resources,
		prompts=prompts,
	)
	if server.scope is MCPServerScope.USER:
		_validate_user_snapshot_limits(capabilities.tools)
	_store_capabilities(server, capabilities)
	return capabilities


def _refresh_snapshot_names(server: MCPServer) -> None:
	capabilities = _capabilities_from_server(server)
	for tool in capabilities.tools:
		tool.normalized_name = normalized_mcp_tool_name(server.name, tool.name)
	for prompt in capabilities.prompts:
		prompt.command = normalized_mcp_prompt_command(
			str(server.id),
			str(prompt.id),
			prompt.name,
		)
	_store_capabilities(server, capabilities)


def _store_capabilities(
	server: MCPServer,
	capabilities: MCPDiscoveredCapabilities,
) -> None:
	set_attribute(
		server,
		"discovered_tools",
		[tool.model_dump(mode="json") for tool in capabilities.tools],
	)
	set_attribute(
		server,
		"discovered_resources",
		[resource.model_dump(mode="json") for resource in capabilities.resources],
	)
	set_attribute(
		server,
		"discovered_prompts",
		[prompt.model_dump(mode="json") for prompt in capabilities.prompts],
	)


def _snapshot_id(
	old_item: MCPDiscoveredTool | MCPDiscoveredResource | MCPDiscoveredPrompt | None,
	prefix: str,
	used_ids: set[str],
) -> TypeID:
	if old_item is not None and str(old_item.id) not in used_ids:
		used_ids.add(str(old_item.id))
		return old_item.id
	while True:
		candidate = new_typeid(prefix)
		if str(candidate) not in used_ids:
			used_ids.add(str(candidate))
			return candidate


def _assert_unique_snapshot_key(
	capability_type: str,
	key: str,
	seen: set[str],
) -> None:
	"""raise when one discovery response repeats a capability key."""
	if key in seen:
		raise ValueError(f"MCP server returned duplicate {capability_type}: {key}")
	seen.add(key)


def _prompt_arguments(arguments: list[JSONObject]) -> list[MCPPromptArgument]:
	"""validate raw MCP prompt argument payloads for snapshot storage."""
	return [MCPPromptArgument.model_validate(argument) for argument in arguments]


def client_config(server: MCPServer) -> MCPClientConfig:
	"""build the raw adapter connection config for one MCP server row."""
	return MCPClientConfig(
		transport=server.transport,
		url=server.url,
		headers=_headers(server),
		timeout=_timeout(server.config.get("timeout", None)),
	)


def _timeout(value: JSONValue) -> float:
	"""resolve and clamp an MCP request timeout from server config."""
	default = float(settings.integrations.mcp.default_timeout_seconds)
	max_timeout = float(settings.integrations.mcp.max_timeout_seconds)
	timeout: float | None = None
	if isinstance(value, bool):
		timeout = None
	elif isinstance(value, int | float):
		timeout = float(value)
	elif isinstance(value, str):
		try:
			timeout = float(value)
		except ValueError:
			timeout = None
	if timeout is None or timeout <= 0 or timeout != timeout:
		return default
	return min(timeout, max_timeout)


def _headers(server: MCPServer) -> dict[str, str]:
	"""build sanitized outbound MCP headers with optional bearer auth."""
	headers = {
		str(key): str(value)
		for key, value in (server.headers or {}).items()
		if isinstance(value, str)
	}
	access_token = _access_token(server)
	if server.auth_type is MCPAuthType.BEARER and access_token:
		headers["Authorization"] = f"Bearer {access_token}"
	return headers


def _surface(server: MCPServer) -> MCPSurfaceConfig:
	"""return enabled MCP capability families for one server row."""
	return MCPSurfaceConfig.model_validate(server.capabilities or {})


def _encrypt_access_token(access_token: str | None) -> str | None:
	"""encrypt a non-empty MCP access token for storage."""
	if access_token is None or access_token.strip() == "":
		return None
	return encrypt_string(access_token, settings.security.secret_key)


def _access_token(server: MCPServer) -> str | None:
	"""decrypt a stored MCP access token when one is configured."""
	if (
		server.encrypted_access_token is None
		or server.encrypted_access_token.strip() == ""
	):
		return None
	plaintext, _ = decrypt_string_with_fallback(
		server.encrypted_access_token,
		settings.security.secret_key,
		settings.security.previous_secret_keys,
	)
	return plaintext


def _validate_server_payload(server_in: MCPServerCreate) -> None:
	_validate_transport(server_in.transport)
	_validate_auth_type(server_in.auth_type)
	_validate_transport_fields(
		server_in.transport,
		server_in.url,
		server_in.command,
		bool(server_in.args),
		bool(server_in.env),
	)


def _validate_user_server_payload(server_in: MCPServerCreate) -> None:
	_validate_server_payload(server_in)
	_validate_user_server_surface(server_in.capabilities)
	_validate_user_server_url(server_in.url)
	_validate_user_server_connection(
		server_in.transport,
		server_in.auth_type,
		server_in.command,
		bool(server_in.args),
		bool(server_in.env),
	)


def _validate_server_update(server: MCPServer, server_in: MCPServerUpdate) -> None:
	transport = (
		server_in.transport
		if isinstance(server_in.transport, MCPTransport)
		else server.transport
	)
	_validate_transport(transport)
	auth_type = (
		server_in.auth_type
		if isinstance(server_in.auth_type, MCPAuthType)
		else server.auth_type
	)
	_validate_auth_type(auth_type)
	url: str | None = server.url
	if "url" in server_in.model_fields_set:
		url = server_in.url if isinstance(server_in.url, str) else None
	command: str | None = server.command
	if "command" in server_in.model_fields_set:
		command = server_in.command if isinstance(server_in.command, str) else None
	args_present = bool(server.args)
	args_value: object = server_in.args
	if "args" in server_in.model_fields_set and isinstance(args_value, list):
		args_present = bool(args_value)
	env_present = bool(server.env)
	env_value: object = server_in.env
	if "env" in server_in.model_fields_set and isinstance(env_value, dict):
		env_present = bool(env_value)
	_validate_transport_fields(transport, url, command, args_present, env_present)


def _validate_user_server_update(server: MCPServer, server_in: MCPServerUpdate) -> None:
	transport = (
		server_in.transport
		if isinstance(server_in.transport, MCPTransport)
		else server.transport
	)
	auth_type = (
		server_in.auth_type
		if isinstance(server_in.auth_type, MCPAuthType)
		else server.auth_type
	)
	command = server.command
	url = server.url
	if "url" in server_in.model_fields_set:
		url = server_in.url if isinstance(server_in.url, str) else None
	if "command" in server_in.model_fields_set:
		command = server_in.command if isinstance(server_in.command, str) else None
	args_present = bool(server.args)
	if "args" in server_in.model_fields_set and isinstance(server_in.args, list):
		args_present = bool(server_in.args)
	env_present = bool(server.env)
	if "env" in server_in.model_fields_set and isinstance(server_in.env, dict):
		env_present = bool(server_in.env)
	_validate_user_server_url(url)
	_validate_user_server_connection(
		transport,
		auth_type,
		command,
		args_present,
		env_present,
	)
	if "capabilities" in server_in.model_fields_set and isinstance(
		server_in.capabilities, MCPSurfaceConfig
	):
		_validate_user_server_surface(server_in.capabilities)


def _validate_user_server_surface(capabilities: MCPSurfaceConfig) -> None:
	if capabilities != _user_mcp_surface():
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="user-owned MCP servers can only expose tools",
		)


def _validate_user_server_connection(
	transport: MCPTransport,
	auth_type: MCPAuthType,
	command: str | None,
	args_present: bool,
	env_present: bool,
) -> None:
	if transport is not MCPTransport.STREAMABLE_HTTP:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="user-owned MCP servers only support streamable HTTP",
		)
	if auth_type is MCPAuthType.OAUTH_2_1:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="user-owned MCP servers do not support OAuth yet",
		)
	if command or args_present or env_present:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="user-owned MCP servers do not support command, args, or env",
		)


def _validate_user_server_url(url: str | None) -> None:
	if url is None:
		return
	origin = _origin_from_url(url)
	origin_mode = settings.integrations.mcp.user_server_origin_mode
	origins = set(settings.integrations.mcp.user_server_origins)
	if origin_mode == "deny" and origin in origins:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="MCP server origin is denied",
		)
	if origin_mode == "allow" and origin not in origins:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="MCP server origin is not allowed",
		)


def _origin_from_url(url: str) -> str:
	parts = urlsplit(url.strip())
	if not parts.scheme or not parts.netloc:
		return url.rstrip("/").lower()
	return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _validate_user_snapshot_limits(tools: list[MCPDiscoveredTool]) -> None:
	max_tools = settings.integrations.mcp.user_server_max_tools
	if len(tools) > max_tools:
		raise ValueError("user-owned MCP server exposes too many tools")
	max_tokens = settings.integrations.mcp.user_tool_definition_max_tokens
	for tool in tools:
		definition = json.dumps(
			{
				"name": tool.name,
				"description": tool.description,
				"parameters": tool.input_schema,
			},
			separators=(",", ":"),
			sort_keys=True,
		)
		if estimate_tokens(definition) > max_tokens:
			raise ValueError("user-owned MCP tool definition is too large")


def _validate_transport(transport: MCPTransport) -> None:
	allowed = settings.integrations.mcp.allowed_transports
	if transport.value not in allowed:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="MCP transport is not allowed",
		)
	if transport is not MCPTransport.STREAMABLE_HTTP:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="MCP transport is not supported yet",
		)


def _validate_auth_type(auth_type: MCPAuthType) -> None:
	if auth_type is MCPAuthType.OAUTH_2_1:
		raise HTTPException(
			status_code=status.HTTP_400_BAD_REQUEST,
			detail="MCP OAuth is not supported yet",
		)


def _validate_transport_fields(
	transport: MCPTransport,
	url: str | None,
	command: str | None,
	args_present: bool,
	env_present: bool,
) -> None:
	if transport is MCPTransport.STREAMABLE_HTTP:
		if not url or url.strip() == "":
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="streamable HTTP MCP requires a URL",
			)
		if command or args_present or env_present:
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="streamable HTTP MCP does not support command, args, or env",
			)
