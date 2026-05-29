"""MCP-backed chat tools."""

from __future__ import annotations

from fastapi import HTTPException
from pydantic_core import to_jsonable_python
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from api.mcp import MCPError
from api.models.mcp import MCPServer, MCPServerScope
from api.schemas.mcp import MCPDiscoveredTool, MCPSurfaceConfig
from api.settings import settings
from api.v1.service.chat.context import AppContext
from api.v1.service.chat.tools.external import ExternalToolSource
from api.v1.service.integrations.mcp.cache import (
	get_cached_mcp_server_tools,
	set_cached_mcp_server_tools,
)
from api.v1.service.integrations.mcp.ids import (
	parse_mcp_server_tools_plugin_id,
	parse_mcp_tool_plugin_id,
)
from api.v1.service.integrations.mcp.service import (
	call_tool,
	get_available_plugin,
	list_available_plugins,
)
from nokodo_ai.agents import AgentIterationSnapshot
from nokodo_ai.context import AgentContext, ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.tool import Tool
from nokodo_ai.types.json import JSONObject


MCP_TOOL_ID_PREFIX = "mcp:"


def mcp_external_tool_source() -> ExternalToolSource:
	"""return the MCP implementation of the external tool source boundary."""
	return ExternalToolSource(
		name="mcp",
		prefix=MCP_TOOL_ID_PREFIX,
		resolve_tools=resolve_mcp_tools_for_context,
		list_plugins=list_available_plugins,
		get_plugin=get_available_plugin,
	)


async def resolve_mcp_tools_for_context(
	tool_ids: list[str],
	app_context: AppContext,
) -> list[Tool[AppContext]]:
	"""resolve MCP plugin ids from a chat app context."""
	return await resolve_mcp_tools(tool_ids, app_context.session)


class MCPRemoteTool(Tool[AppContext]):
	"""chat tool backed by one MCP server tool."""

	server_id: str
	mcp_tool_id: str
	mcp_tool_name: str

	async def call(
		self,
		__state__: AgentIterationSnapshot[AppContext],
		__agent_context__: AgentContext,
		__tool_call_context__: ToolCallContext,
		__app_context__: AppContext | None,
		**kwargs: object,
	) -> ToolMessage:
		"""call the backing MCP tool."""
		if __app_context__ is None:
			return self.error("app context is required", __tool_call_context__)
		json_arguments = to_jsonable_python(kwargs, exclude_none=True, fallback=str)
		arguments: JSONObject = (
			json_arguments if isinstance(json_arguments, dict) else {}
		)
		try:
			result = await call_tool(
				self.server_id,
				self.mcp_tool_id,
				self.mcp_tool_name,
				arguments,
				__app_context__.session,
			)
		except HTTPException as exc:
			return self.error(str(exc.detail), __tool_call_context__)
		except (MCPError, SQLAlchemyError, OSError, ValueError) as exc:
			return self.error(str(exc), __tool_call_context__)
		if result.is_error:
			return self.error(result.as_output_text(), __tool_call_context__)
		return self.success(result.as_output_text(), __tool_call_context__)


async def resolve_mcp_tools(
	tool_ids: list[str],
	session: AsyncSession,
) -> list[Tool[AppContext]]:
	"""resolve MCP plugin ids into chat tools."""
	if not settings.integrations.mcp.enabled:
		return []
	tools: list[Tool[AppContext]] = []
	tool_refs: set[tuple[str, str]] = set()
	server_ids: set[str] = set()
	for tool_id in tool_ids:
		tool_ref = parse_mcp_tool_plugin_id(tool_id)
		if tool_ref is not None:
			tool_refs.add(tool_ref)
		server_id = parse_mcp_server_tools_plugin_id(tool_id)
		if server_id is not None:
			server_ids.add(server_id)
	wanted_server_ids = server_ids | {server_id for server_id, _ in tool_refs}
	if not wanted_server_ids:
		return tools
	server_tools = await _load_server_tools(wanted_server_ids, session)
	seen_tools: set[tuple[str, str]] = set()
	for server_id, mcp_tool_id in tool_refs:
		tool = _find_enabled_tool(server_tools.get(server_id, []), mcp_tool_id)
		if tool is None:
			continue
		seen_tools.add((server_id, mcp_tool_id))
		tools.append(_tool_from_snapshot(server_id, tool))
	for server_id in server_ids:
		for tool in server_tools.get(server_id, []):
			key = (server_id, str(tool.id))
			if key in seen_tools:
				continue
			seen_tools.add(key)
			tools.append(_tool_from_snapshot(server_id, tool))
	return tools


async def _load_server_tools(
	server_ids: set[str],
	session: AsyncSession,
) -> dict[str, list[MCPDiscoveredTool]]:
	"""load enabled tool snapshots for MCP servers, preferring Redis cache."""
	server_tools: dict[str, list[MCPDiscoveredTool]] = {}
	missing_ids: set[str] = set()
	for server_id in server_ids:
		cached = await get_cached_mcp_server_tools(session, server_id)
		if cached is None:
			missing_ids.add(server_id)
		else:
			server_tools[server_id] = cached
	if not missing_ids:
		return server_tools
	result = await session.execute(
		select(MCPServer).where(
			MCPServer.scope == MCPServerScope.GLOBAL,
			MCPServer.enabled.is_(True),
			MCPServer.id.in_(missing_ids),
		)
	)
	for server in result.scalars().all():
		server_id = str(server.id)
		tools = _enabled_tools(server)
		server_tools[server_id] = tools
		await set_cached_mcp_server_tools(session, server_id, tools)
	return server_tools


def _enabled_tools(server: MCPServer) -> list[MCPDiscoveredTool]:
	"""return enabled discovered tool snapshots for an enabled MCP server row."""
	if not MCPSurfaceConfig.model_validate(server.capabilities or {}).tools:
		return []
	return [
		tool
		for tool in (
			MCPDiscoveredTool.model_validate(item)
			for item in (server.discovered_tools or [])
		)
		if tool.enabled
	]


def _find_enabled_tool(
	tools: list[MCPDiscoveredTool],
	mcp_tool_id: str,
) -> MCPDiscoveredTool | None:
	"""find one enabled MCP tool snapshot by embedded snapshot id."""
	for tool in tools:
		if str(tool.id) == mcp_tool_id:
			return tool
	return None


def _tool_from_snapshot(server_id: str, tool: MCPDiscoveredTool) -> MCPRemoteTool:
	"""build a runtime chat tool from a cached MCP tool snapshot."""
	return MCPRemoteTool(
		name=tool.normalized_name,
		description=tool.description or "MCP tool",
		parameters=tool.input_schema,
		server_id=server_id,
		mcp_tool_id=str(tool.id),
		mcp_tool_name=tool.name,
	)
