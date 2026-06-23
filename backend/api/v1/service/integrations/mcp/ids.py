"""MCP plugin id helpers.

the tool and aggregate plugin id format is owned by `api.schemas.mcp` (the
lowest layer that serializes these ids) and re-exported here so the service and
runtime keep importing from one place.
"""

from __future__ import annotations

from api.schemas.mcp import (
	MCP_SERVER_TOOLS_PREFIX,
	MCP_SERVER_TOOLS_SUFFIX,
	MCP_TOOL_PREFIX,
	mcp_server_tools_plugin_id,
	mcp_tool_plugin_id,
)


MCP_PROMPT_PREFIX = "mcp:prompt:"


__all__ = [
	"MCP_PROMPT_PREFIX",
	"MCP_SERVER_TOOLS_PREFIX",
	"MCP_SERVER_TOOLS_SUFFIX",
	"MCP_TOOL_PREFIX",
	"mcp_prompt_plugin_id",
	"mcp_server_tools_plugin_id",
	"mcp_tool_plugin_id",
	"parse_mcp_prompt_plugin_id",
	"parse_mcp_server_tools_plugin_id",
	"parse_mcp_tool_plugin_id",
]


def mcp_prompt_plugin_id(server_id: str, prompt_id: str) -> str:
	"""return the plugin id for one MCP prompt snapshot."""
	return f"{MCP_PROMPT_PREFIX}{server_id}:{prompt_id}"


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
