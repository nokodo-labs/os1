"""MCP plugin id helpers."""

from __future__ import annotations


MCP_TOOL_PREFIX = "mcp:tool:"
MCP_PROMPT_PREFIX = "mcp:prompt:"
MCP_SERVER_TOOLS_PREFIX = "mcp:server:"
MCP_SERVER_TOOLS_SUFFIX = ":tools"


def mcp_tool_plugin_id(server_id: str, tool_id: str) -> str:
	"""return the plugin id for one MCP tool snapshot."""
	return f"{MCP_TOOL_PREFIX}{server_id}:{tool_id}"


def mcp_prompt_plugin_id(server_id: str, prompt_id: str) -> str:
	"""return the plugin id for one MCP prompt snapshot."""
	return f"{MCP_PROMPT_PREFIX}{server_id}:{prompt_id}"


def mcp_server_tools_plugin_id(server_id: str) -> str:
	"""return the plugin id for all enabled tools from one MCP server."""
	return f"{MCP_SERVER_TOOLS_PREFIX}{server_id}{MCP_SERVER_TOOLS_SUFFIX}"


def parse_mcp_tool_plugin_id(plugin_id: str) -> tuple[str, str] | None:
	"""extract server and tool ids from an MCP tool plugin id."""
	if not plugin_id.startswith(MCP_TOOL_PREFIX):
		return None
	ids = plugin_id[len(MCP_TOOL_PREFIX) :]
	server_id, sep, tool_id = ids.partition(":")
	if not sep or not server_id or not tool_id:
		return None
	return server_id, tool_id


def parse_mcp_prompt_plugin_id(plugin_id: str) -> tuple[str, str] | None:
	"""extract server and prompt ids from an MCP prompt plugin id."""
	if not plugin_id.startswith(MCP_PROMPT_PREFIX):
		return None
	ids = plugin_id[len(MCP_PROMPT_PREFIX) :]
	server_id, sep, prompt_id = ids.partition(":")
	if not sep or not server_id or not prompt_id:
		return None
	return server_id, prompt_id


def parse_mcp_server_tools_plugin_id(plugin_id: str) -> str | None:
	"""extract server id from an MCP all-tools plugin id."""
	if not plugin_id.startswith(MCP_SERVER_TOOLS_PREFIX):
		return None
	if not plugin_id.endswith(MCP_SERVER_TOOLS_SUFFIX):
		return None
	server_id = plugin_id[len(MCP_SERVER_TOOLS_PREFIX) : -len(MCP_SERVER_TOOLS_SUFFIX)]
	return server_id or None
