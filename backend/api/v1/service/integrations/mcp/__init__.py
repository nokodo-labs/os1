"""MCP service package."""

from api.v1.service.chat.tools.external import register_external_tool_source
from api.v1.service.integrations.mcp.ids import (
	MCP_PROMPT_PREFIX,
	MCP_SERVER_TOOLS_PREFIX,
	MCP_TOOL_PREFIX,
	mcp_prompt_plugin_id,
	mcp_server_tools_plugin_id,
	mcp_tool_plugin_id,
	parse_mcp_prompt_plugin_id,
	parse_mcp_server_tools_plugin_id,
	parse_mcp_tool_plugin_id,
)
from api.v1.service.integrations.mcp.lifecycle import initialize_global_mcp_servers
from api.v1.service.integrations.mcp.listeners import (
	start_mcp_list_change_listeners,
	stop_mcp_list_change_listeners,
)
from api.v1.service.integrations.mcp.prompts import mcp_external_prompt_source
from api.v1.service.integrations.mcp.service import (
	client_config,
	create_server,
	delete_server,
	discover_server,
	get_available_plugin,
	get_server,
	list_available_plugins,
	list_capabilities,
	list_servers,
	update_capability,
	update_server,
)
from api.v1.service.integrations.mcp.tools import (
	mcp_external_tool_source,
	resolve_mcp_tools,
)
from api.v1.service.prompts import register_external_prompt_source


register_external_tool_source(mcp_external_tool_source())
register_external_prompt_source(mcp_external_prompt_source())


__all__ = [
	"MCP_SERVER_TOOLS_PREFIX",
	"MCP_PROMPT_PREFIX",
	"MCP_TOOL_PREFIX",
	"client_config",
	"create_server",
	"delete_server",
	"discover_server",
	"get_available_plugin",
	"get_server",
	"initialize_global_mcp_servers",
	"list_available_plugins",
	"list_capabilities",
	"list_servers",
	"mcp_prompt_plugin_id",
	"mcp_server_tools_plugin_id",
	"mcp_tool_plugin_id",
	"parse_mcp_prompt_plugin_id",
	"parse_mcp_server_tools_plugin_id",
	"parse_mcp_tool_plugin_id",
	"resolve_mcp_tools",
	"start_mcp_list_change_listeners",
	"stop_mcp_list_change_listeners",
	"update_capability",
	"update_server",
]
