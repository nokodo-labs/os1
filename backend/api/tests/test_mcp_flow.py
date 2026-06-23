"""MCP user-flow tests."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_attribute

from api.mcp import MCPClientConfig, MCPError, MCPListChangedEvent
from api.mcp.types import (
	MCPCapabilitySnapshot,
	MCPPromptRenderResult,
	MCPPromptSpec,
	MCPResourceSpec,
	MCPToolCallResult,
	MCPToolSpec,
)
from api.models.mcp import MCPAuthType, MCPServer, MCPServerScope, MCPServerStatus
from api.models.user import User
from api.permissions import ActionPermission
from api.schemas.agent import AgentConfig, AgentFeatures, UserMCPToolsFeature
from api.schemas.mcp import (
	MCPCapabilityType,
	MCPCapabilityUpdate,
	MCPServerCreate,
	MCPServerUpdate,
	MCPSurfaceConfig,
)
from api.schemas.plugin import PluginListFilters
from api.settings import settings
from api.v1.service import plugins as plugin_service
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.integrations.mcp import lifecycle as mcp_lifecycle
from api.v1.service.integrations.mcp import listeners as mcp_listeners
from api.v1.service.integrations.mcp import prompts as mcp_prompts
from api.v1.service.integrations.mcp import service as mcp_service
from api.v1.service.integrations.mcp.cache import invalidate_mcp_cache
from api.v1.service.integrations.mcp.ids import mcp_tool_plugin_id
from api.v1.service.integrations.mcp.tools import (
	MCPRemoteTool,
	resolve_mcp_extra_tools,
	resolve_mcp_tools,
)
from api.v1.service.prompts import (
	load_external_prompt_placeholders,
	render_external_prompt_content_map,
	render_inline_with_prompts,
)
from nokodo_ai import AgentContext, AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import new_typeid


async def _principal(
	session: AsyncSession,
	permissions: frozenset[str],
) -> Principal:
	"""create a non-admin principal with explicit action permissions."""
	user_id = new_typeid("user")
	user = User(
		email=f"{user_id}@example.com",
		username=f"mcp_{user_id.replace('_', '')[:20]}",
		hashed_password="x",
		is_superuser=False,
	)
	session.add(user)
	await session.flush()
	await session.refresh(user)
	return Principal(user=user, group_ids=(), permissions=permissions)


def _auth_headers(auth: dict[str, object]) -> dict[str, str]:
	"""return auth headers from an API auth fixture."""
	raw_headers = auth["headers"]
	assert isinstance(raw_headers, dict)
	return {str(key): str(value) for key, value in raw_headers.items()}


def _state() -> AgentIterationSnapshot[AppContext]:
	"""create a minimal agent iteration snapshot for MCP tool calls."""
	return AgentIterationState[AppContext](thread=Thread(), tools=[]).snapshot()


def _agent_context() -> AgentContext:
	"""create a minimal agent context for MCP tool calls."""
	return AgentContext(model=ChatModel.model_construct(model_name="stub"))


def _tool_call_context() -> ToolCallContext:
	"""create a minimal tool call context for MCP tool calls."""
	return ToolCallContext(tool_call_id="tool-call", tool_call_start_time=0.0)


async def _noop_event_emitter(event: object) -> None:
	"""accept emitted events without recording them."""
	_ = event


def _app_context(session: AsyncSession) -> AppContext:
	"""create an app context backed by the active API test session."""
	user = User(
		id=new_typeid("user"),
		email="mcp-endpoint@example.com",
		username="mcp_endpoint_user",
		hashed_password="x",
		is_superuser=True,
	)
	return AppContext(
		session=session,
		principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		event_emitter=_noop_event_emitter,
	)


def _app_context_for_principal(
	session: AsyncSession,
	principal: Principal,
) -> AppContext:
	"""create an app context for a specific principal."""
	return AppContext(
		session=session,
		principal=principal,
		event_emitter=_noop_event_emitter,
	)


def _user_mcp_agent_config(enabled: bool) -> AgentConfig:
	"""build agent config for user MCP extra tool tests."""
	return AgentConfig(
		features=AgentFeatures(
			user_mcp_tools=UserMCPToolsFeature(enabled=enabled),
		)
	)


class _DiscoveryClient:
	"""fake MCP client that returns all supported capability families."""

	def __init__(self, config: MCPClientConfig) -> None:
		"""store the client config for parity with the real MCP client."""
		self.config = config

	async def __aenter__(self) -> _DiscoveryClient:
		"""return this fake client from the async context manager."""
		return self

	async def __aexit__(
		self,
		exc_type: object,
		exc: object,
		tb: object,
	) -> None:
		"""exit the fake client context without cleanup."""
		return None

	async def discover(
		self,
		include_resources: bool,
		include_prompts: bool,
	) -> MCPCapabilitySnapshot:
		"""return a snapshot containing one tool, resource, and prompt."""
		assert include_resources is True
		assert include_prompts is True
		return MCPCapabilitySnapshot(
			tools=[MCPToolSpec("lookup", "look up data", {})],
			resources=[
				MCPResourceSpec(
					uri="file:///docs/readme.md",
					name="readme",
					description="project readme",
					mime_type="text/markdown",
				)
			],
			prompts=[MCPPromptSpec("brief", "write a brief", [])],
		)

	async def get_prompt(
		self,
		name: str,
		arguments: dict[str, str] | None = None,
	) -> MCPPromptRenderResult:
		"""return rendered prompt content for catalog tests."""
		assert arguments is None
		return MCPPromptRenderResult(
			description=f"rendered {name}",
			text=f"rendered {name}",
		)


class _RuntimeClient:
	"""fake MCP client for endpoint-to-runtime flow tests."""

	tool_calls: list[tuple[str, JSONObject]] = []
	prompt_calls: list[str] = []
	configs: list[MCPClientConfig] = []

	def __init__(self, config: MCPClientConfig) -> None:
		"""record each client config produced from the persisted server."""
		self.config = config
		self.__class__.configs.append(config)

	@classmethod
	def reset(cls) -> None:
		"""clear call records between tests."""
		cls.tool_calls = []
		cls.prompt_calls = []
		cls.configs = []

	async def __aenter__(self) -> _RuntimeClient:
		"""return this fake client from the async context manager."""
		return self

	async def __aexit__(
		self,
		exc_type: object,
		exc: object,
		tb: object,
	) -> None:
		"""exit the fake client context without cleanup."""
		return None

	def _assert_http_config(self) -> None:
		assert self.config.url == "https://example.test/mcp"
		assert self.config.headers["Authorization"] == "Bearer secret-token"

	async def discover(
		self,
		include_resources: bool,
		include_prompts: bool,
	) -> MCPCapabilitySnapshot:
		"""return capabilities as if they came from a remote MCP server."""
		self._assert_http_config()
		assert include_resources is True
		assert include_prompts is True
		input_schema: JSONObject = {
			"type": "object",
			"properties": {"query": {"type": "string"}},
			"required": ["query"],
		}
		return MCPCapabilitySnapshot(
			tools=[MCPToolSpec("lookup", "look up remote data", input_schema)],
			resources=[
				MCPResourceSpec(
					uri="file:///docs/remote.md",
					name="remote doc",
					description="remote MCP resource",
					mime_type="text/markdown",
				)
			],
			prompts=[MCPPromptSpec("brief", "write a remote brief", [])],
		)

	async def call_tool(
		self,
		name: str,
		arguments: JSONObject,
	) -> MCPToolCallResult:
		"""record the remote tool call and return a structured result."""
		self._assert_http_config()
		self.__class__.tool_calls.append((name, arguments))
		structured_content: JSONObject = {"source": "mcp", "arguments": arguments}
		return MCPToolCallResult(
			is_error=False,
			text="remote lookup complete",
			structured_content=structured_content,
		)

	async def get_prompt(
		self,
		name: str,
		arguments: dict[str, str] | None = None,
	) -> MCPPromptRenderResult:
		"""record prompt rendering and return remote content."""
		self._assert_http_config()
		assert arguments is None
		self.__class__.prompt_calls.append(name)
		return MCPPromptRenderResult(
			description=f"rendered {name}",
			text=f"remote prompt {name}",
		)


class _FailingPromptClient(_DiscoveryClient):
	"""fake MCP client that fails prompt rendering."""

	async def get_prompt(
		self,
		name: str,
		arguments: dict[str, str] | None = None,
	) -> MCPPromptRenderResult:
		"""raise an MCP error for prompt rendering."""
		_ = name, arguments
		raise MCPError("prompt render failed")


class _ListChangedClient:
	"""fake MCP client that emits one tool list-changed notification."""

	def __init__(
		self,
		config: MCPClientConfig,
		receive_events: bool = False,
	) -> None:
		self.config = config
		self._receive_events = receive_events

	async def __aenter__(self) -> _ListChangedClient:
		return self

	async def __aexit__(
		self,
		exc_type: object,
		exc: object,
		tb: object,
	) -> None:
		return None

	async def events(self) -> AsyncIterator[MCPListChangedEvent]:
		"""yield one normalized list-changed event, then wait for cancellation."""
		assert self._receive_events is True
		yield MCPListChangedEvent(kind="tools")
		await asyncio.Event().wait()


async def _create_discovered_server(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> MCPServer:
	"""create and discover an MCP server for cache flow tests."""
	monkeypatch.setattr(mcp_service, "MCPClient", _DiscoveryClient)
	principal = await _principal(
		db_session,
		frozenset({ActionPermission.MCP_MANAGE}),
	)
	server_name = f"flow-{new_typeid('mcpsrv')}"
	server = await mcp_service.create_server(
		MCPServerCreate(
			name=server_name,
			url="https://example.test/mcp",
			access_token="secret-token",
			capabilities=MCPSurfaceConfig(
				tools=True,
				resources=True,
				prompts=True,
			),
		),
		db_session,
		principal=principal,
	)
	await mcp_service.discover_server(server.id, db_session, principal=principal)
	await db_session.commit()
	return server


async def _create_user_mcp_tool_server(
	db_session: AsyncSession,
	principal: Principal,
	name: str,
) -> tuple[MCPServer, str]:
	"""create a user-owned MCP server with one discovered tool snapshot."""
	server = await mcp_service.create_server(
		MCPServerCreate(
			name=name,
			scope=MCPServerScope.USER,
			url="https://example.test/mcp",
			auth_type=MCPAuthType.BEARER,
			access_token="secret-token",
			capabilities=MCPSurfaceConfig(
				tools=True,
				resources=False,
				prompts=False,
				sampling=False,
			),
		),
		db_session,
		principal=principal,
	)
	tool_id = new_typeid("mcptool")
	server.status = MCPServerStatus.READY
	set_attribute(
		server,
		"discovered_tools",
		[
			{
				"id": tool_id,
				"name": "lookup",
				"normalized_name": f"{name.lower().replace(' ', '_')}_lookup",
				"description": "look up owned data",
				"input_schema": {
					"type": "object",
					"properties": {"query": {"type": "string"}},
				},
				"output_schema": None,
				"enabled": True,
				"schema_hash": "owned-tool",
				"last_discovered_at": None,
			}
		],
	)
	db_session.add(server)
	await db_session.flush()
	return server, mcp_tool_plugin_id(str(server.id), tool_id)


@pytest.mark.asyncio
async def test_mcp_endpoint_discovery_hydrates_catalogs_and_runtime_objects(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP endpoint discovery hydrates external catalogs and usable runtime objects."""
	await invalidate_mcp_cache(db_session)
	_RuntimeClient.reset()
	monkeypatch.setattr(mcp_service, "MCPClient", _RuntimeClient)
	monkeypatch.setattr(mcp_prompts, "MCPClient", _RuntimeClient)
	headers = _auth_headers(admin_auth)

	created = await client.post(
		"/v1/integrations/mcp/servers",
		headers=headers,
		json={
			"name": "Endpoint MCP",
			"description": "endpoint flow server",
			"url": "https://example.test/mcp",
			"auth_type": "bearer",
			"access_token": "secret-token",
			"capabilities": {
				"tools": True,
				"resources": True,
				"prompts": True,
				"sampling": False,
			},
		},
	)
	assert created.status_code == 201
	server = created.json()
	server_id = str(server["id"])
	assert server["has_credentials"] is True
	assert "access_token" not in server

	discovered = await client.post(
		f"/v1/integrations/mcp/servers/{server_id}/discover",
		headers=headers,
	)
	assert discovered.status_code == 200
	discovery = discovered.json()
	assert discovery["server"]["status"] == "ready"
	assert discovery["server"]["has_credentials"] is True

	capabilities = discovery["capabilities"]
	assert [tool["name"] for tool in capabilities["tools"]] == ["lookup"]
	assert [prompt["name"] for prompt in capabilities["prompts"]] == ["brief"]
	assert [resource["uri"] for resource in capabilities["resources"]] == [
		"file:///docs/remote.md"
	]
	tool_snapshot = capabilities["tools"][0]
	prompt_snapshot = capabilities["prompts"][0]
	tool_plugin_id = mcp_tool_plugin_id(server_id, str(tool_snapshot["id"]))
	prompt_command = str(prompt_snapshot["command"])

	listed_capabilities = await client.get(
		f"/v1/integrations/mcp/servers/{server_id}/capabilities",
		headers=headers,
	)
	assert listed_capabilities.status_code == 200
	assert listed_capabilities.json()["tools"][0]["id"] == tool_snapshot["id"]

	plugins = await client.get(
		"/v1/plugins",
		headers=headers,
		params={"source": "external", "plugin_type": "tool"},
	)
	assert plugins.status_code == 200
	plugin_ids = {str(plugin["id"]) for plugin in plugins.json()}
	assert tool_plugin_id in plugin_ids

	plugin_detail = await client.get(f"/v1/plugins/{tool_plugin_id}", headers=headers)
	assert plugin_detail.status_code == 200
	assert plugin_detail.json() == {
		"id": tool_plugin_id,
		"name": "Endpoint MCP: lookup",
		"description": "look up remote data",
		"source": "external",
		"type": "tool",
	}

	prompts = await client.get(
		"/v1/prompts",
		headers=headers,
		params={"source": "external"},
	)
	assert prompts.status_code == 200
	assert prompt_command in {str(prompt["id"]) for prompt in prompts.json()}

	prompt_detail = await client.get(f"/v1/prompts/{prompt_command}", headers=headers)
	assert prompt_detail.status_code == 200
	assert prompt_detail.json()["content"] == "remote prompt brief"

	rendered_inline = await render_inline_with_prompts(
		db_session,
		text=f"before {{% include '{prompt_command}' %}} after",
	)
	assert rendered_inline == "before remote prompt brief after"

	runtime_tools = await resolve_mcp_tools([tool_plugin_id], db_session)
	assert len(runtime_tools) == 1
	runtime_tool = runtime_tools[0]
	assert isinstance(runtime_tool, MCPRemoteTool)
	assert runtime_tool.mcp_tool_name == "lookup"
	assert runtime_tool.parameters == tool_snapshot["input_schema"]

	message = await runtime_tool.call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		_app_context(db_session),
		query="alpha",
	)
	assert isinstance(message, ToolMessage)
	assert not message.is_error
	assert json.loads(message.tool_output) == {
		"text": "remote lookup complete",
		"structured_content": {
			"source": "mcp",
			"arguments": {"query": "alpha"},
		},
	}
	assert _RuntimeClient.tool_calls == [("lookup", {"query": "alpha"})]
	assert "brief" in _RuntimeClient.prompt_calls
	assert all(
		config.url == "https://example.test/mcp"
		and config.headers["Authorization"] == "Bearer secret-token"
		for config in _RuntimeClient.configs
	)


@pytest.mark.asyncio
async def test_user_mcp_permission_sees_only_owned_mcp_tool_plugins(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""user.mcp:manage sees only owned user MCP tools in the plugin catalog."""
	await invalidate_mcp_cache(db_session)
	owner = await _principal(
		db_session,
		frozenset({ActionPermission.USER_MCP_MANAGE}),
	)
	other = await _principal(
		db_session,
		frozenset({ActionPermission.USER_MCP_MANAGE}),
	)
	admin = await _principal(
		db_session,
		frozenset({ActionPermission.MCP_MANAGE, ActionPermission.PLUGINS_READ}),
	)
	owned_server, owned_plugin_id = await _create_user_mcp_tool_server(
		db_session, owner, "Owned MCP"
	)
	other_server, other_plugin_id = await _create_user_mcp_tool_server(
		db_session, other, "Other MCP"
	)
	global_server = await mcp_service.create_server(
		MCPServerCreate(
			name="Global MCP",
			url="https://example.test/mcp",
			capabilities=MCPSurfaceConfig(tools=True),
		),
		db_session,
		principal=admin,
	)
	global_tool_id = new_typeid("mcptool")
	global_plugin_id = mcp_tool_plugin_id(str(global_server.id), global_tool_id)
	global_server.status = MCPServerStatus.READY
	set_attribute(
		global_server,
		"discovered_tools",
		[
			{
				"id": global_tool_id,
				"name": "global_lookup",
				"normalized_name": "global_mcp_global_lookup",
				"description": "global tool",
				"input_schema": {},
				"output_schema": None,
				"enabled": True,
				"schema_hash": "global-tool",
				"last_discovered_at": None,
			}
		],
	)
	db_session.add(global_server)
	await db_session.flush()

	plugins = await plugin_service.list_plugins(
		db_session,
		principal=owner,
		include_native=True,
		filters=PluginListFilters(),
	)
	plugin_ids = {plugin.id for plugin in plugins}
	assert plugin_ids == {owned_plugin_id}
	assert other_plugin_id not in plugin_ids
	assert global_plugin_id not in plugin_ids
	assert plugins[0].name == f"{owned_server.name}: lookup"

	admin_plugins = await plugin_service.list_plugins(
		db_session,
		principal=admin,
		include_native=True,
		filters=PluginListFilters(source="external", plugin_type="tool"),
	)
	admin_plugin_ids = {plugin.id for plugin in admin_plugins}
	assert global_plugin_id in admin_plugin_ids
	assert owned_plugin_id not in admin_plugin_ids
	assert other_plugin_id not in admin_plugin_ids
	assert other_server.owner_user_id == str(other.user_id)


@pytest.mark.asyncio
async def test_extra_plugins_resolve_only_allowed_owned_user_mcp_tools(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""extra_plugins can attach owned user MCP tools only when the agent opts in."""
	await invalidate_mcp_cache(db_session)
	_RuntimeClient.reset()
	monkeypatch.setattr(mcp_service, "MCPClient", _RuntimeClient)
	owner = await _principal(
		db_session,
		frozenset({ActionPermission.USER_MCP_MANAGE}),
	)
	other = await _principal(
		db_session,
		frozenset({ActionPermission.USER_MCP_MANAGE}),
	)
	_, owned_plugin_id = await _create_user_mcp_tool_server(
		db_session, owner, "Owned Runtime MCP"
	)
	_, other_plugin_id = await _create_user_mcp_tool_server(
		db_session, other, "Other Runtime MCP"
	)

	disabled_tools = await resolve_mcp_extra_tools(
		[owned_plugin_id],
		_app_context_for_principal(db_session, owner),
		_user_mcp_agent_config(False),
	)
	assert disabled_tools == []

	resolved_tools = await resolve_mcp_extra_tools(
		[owned_plugin_id, other_plugin_id, "think"],
		_app_context_for_principal(db_session, owner),
		_user_mcp_agent_config(True),
	)
	assert len(resolved_tools) == 1
	runtime_tool = resolved_tools[0]
	assert isinstance(runtime_tool, MCPRemoteTool)
	assert runtime_tool.mcp_tool_name == "lookup"

	message = await runtime_tool.call(
		_state(),
		_agent_context(),
		_tool_call_context(),
		_app_context_for_principal(db_session, owner),
		query="beta",
	)
	assert isinstance(message, ToolMessage)
	assert not message.is_error
	assert _RuntimeClient.tool_calls == [("lookup", {"query": "beta"})]


@pytest.mark.asyncio
async def test_mcp_delete_endpoint_removes_server_from_external_catalogs(
	client: AsyncClient,
	admin_auth: dict[str, object],
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""deleting an MCP server removes its plugin and prompt catalog entries."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	headers = _auth_headers(admin_auth)
	tool_snapshot = server.discovered_tools[0]
	prompt_snapshot = server.discovered_prompts[0]
	tool_plugin_id = mcp_tool_plugin_id(str(server.id), str(tool_snapshot["id"]))
	prompt_command = str(prompt_snapshot["command"])

	plugins_before = await client.get(
		"/v1/plugins",
		headers=headers,
		params={"source": "external", "plugin_type": "tool"},
	)
	assert plugins_before.status_code == 200
	assert tool_plugin_id in {str(plugin["id"]) for plugin in plugins_before.json()}
	assert prompt_command in await load_external_prompt_placeholders(db_session)

	deleted = await client.delete(
		f"/v1/integrations/mcp/servers/{server.id}",
		headers=headers,
	)
	assert deleted.status_code == 204

	missing = await client.get(
		f"/v1/integrations/mcp/servers/{server.id}",
		headers=headers,
	)
	assert missing.status_code == 404
	plugins_after = await client.get(
		"/v1/plugins",
		headers=headers,
		params={"source": "external", "plugin_type": "tool"},
	)
	assert plugins_after.status_code == 200
	assert tool_plugin_id not in {str(plugin["id"]) for plugin in plugins_after.json()}
	assert prompt_command not in await load_external_prompt_placeholders(db_session)


@pytest.mark.asyncio
async def test_mcp_startup_lifecycle_discovers_enabled_servers(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""startup discovery runs only when enabled and only for enabled servers."""
	principal = await _principal(
		db_session,
		frozenset({ActionPermission.MCP_MANAGE}),
	)
	enabled_server = await mcp_service.create_server(
		MCPServerCreate(name="startup-enabled", url="https://example.test/mcp"),
		db_session,
		principal=principal,
	)
	disabled_server = await mcp_service.create_server(
		MCPServerCreate(
			name="startup-disabled",
			url="https://example.test/disabled-mcp",
			enabled=False,
		),
		db_session,
		principal=principal,
	)
	discovered_ids: list[str] = []

	async def discover_server_unchecked(
		server: MCPServer,
		session: AsyncSession,
	) -> object:
		assert session is db_session
		discovered_ids.append(str(server.id))
		return object()

	monkeypatch.setattr(
		mcp_lifecycle,
		"discover_server_unchecked",
		discover_server_unchecked,
	)
	monkeypatch.setattr(settings.integrations.mcp, "enabled", True)
	monkeypatch.setattr(
		settings.integrations.mcp,
		"startup_discovery_enabled",
		False,
	)

	await mcp_lifecycle.initialize_global_mcp_servers(db_session)
	assert discovered_ids == []

	monkeypatch.setattr(
		settings.integrations.mcp,
		"startup_discovery_enabled",
		True,
	)
	await mcp_lifecycle.initialize_global_mcp_servers(db_session)
	assert discovered_ids == [str(enabled_server.id)]
	assert str(disabled_server.id) not in discovered_ids


@pytest.mark.asyncio
async def test_mcp_manage_principal_can_manage_and_discover_server(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""a principal with mcp:manage can create, update, discover, and read MCP data."""
	monkeypatch.setattr(mcp_service, "MCPClient", _DiscoveryClient)
	principal = await _principal(
		db_session,
		frozenset({ActionPermission.MCP_MANAGE}),
	)
	server_name = f"flow-{new_typeid('mcpsrv')}"

	server = await mcp_service.create_server(
		MCPServerCreate(
			name=server_name,
			url="https://example.test/mcp",
			access_token="secret-token",
			capabilities=MCPSurfaceConfig(
				tools=True,
				resources=True,
				prompts=True,
			),
		),
		db_session,
		principal=principal,
	)

	servers = await mcp_service.list_servers(db_session, principal=principal)
	assert server.id in {item.id for item in servers}
	assert server.has_credentials

	updated = await mcp_service.update_server(
		server.id,
		MCPServerUpdate(name=f"{server_name}-updated"),
		db_session,
		principal=principal,
	)
	assert updated.name == f"{server_name}-updated"
	assert updated.status is MCPServerStatus.DISCONNECTED

	discovery = await mcp_service.discover_server(
		server.id,
		db_session,
		principal=principal,
	)
	capabilities = await mcp_service.list_capabilities(
		server.id,
		db_session,
		principal=principal,
	)

	assert discovery.server.status is MCPServerStatus.READY
	assert [tool.name for tool in capabilities.tools] == ["lookup"]
	assert [resource.uri for resource in capabilities.resources] == [
		"file:///docs/readme.md"
	]
	assert capabilities.resources[0].mime_type == "text/markdown"
	assert [prompt.name for prompt in capabilities.prompts] == ["brief"]

	toggled = await mcp_service.update_capability(
		server.id,
		MCPCapabilityType.TOOL,
		capabilities.tools[0].id,
		MCPCapabilityUpdate(enabled=False),
		db_session,
		principal=principal,
	)
	assert toggled.discovered_tools[0]["enabled"] is False


@pytest.mark.asyncio
async def test_mcp_tool_resolution_uses_cached_snapshot_after_first_load(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP tool resolution avoids a second DB read after caching snapshots."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	tool_id = str(server.discovered_tools[0]["id"])
	plugin_id = mcp_tool_plugin_id(str(server.id), tool_id)

	tools = await resolve_mcp_tools([plugin_id], db_session)
	assert len(tools) == 1
	assert isinstance(tools[0], MCPRemoteTool)

	with patch.object(
		db_session,
		"execute",
		new=AsyncMock(side_effect=AssertionError("unexpected DB read")),
	):
		cached_tools = await resolve_mcp_tools([plugin_id], db_session)

	assert len(cached_tools) == 1
	assert isinstance(cached_tools[0], MCPRemoteTool)


@pytest.mark.asyncio
async def test_mcp_prompt_placeholders_use_cached_refs_after_first_load(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP prompt placeholder loading avoids a second DB read after caching refs."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	command = str(server.discovered_prompts[0]["command"])

	placeholders = await load_external_prompt_placeholders(db_session)
	assert command in placeholders

	with patch.object(
		db_session,
		"execute",
		new=AsyncMock(side_effect=AssertionError("unexpected DB read")),
	):
		cached_placeholders = await load_external_prompt_placeholders(db_session)

	assert cached_placeholders == placeholders


@pytest.mark.asyncio
async def test_mcp_prompt_catalog_lists_and_renders_prompt_content(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP prompt catalog exposes discovered prompts and renders prompt detail."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	command = str(server.discovered_prompts[0]["command"])
	monkeypatch.setattr(mcp_prompts, "MCPClient", _DiscoveryClient)

	catalog = await mcp_prompts.list_prompt_catalog(db_session)
	rendered = await render_external_prompt_content_map(db_session, {command})
	detail = await mcp_prompts.get_prompt_catalog(command, db_session)
	missing = await mcp_prompts.get_prompt_catalog("mcp-missing", db_session)

	assert [prompt.id for prompt in catalog] == [command]
	assert catalog[0].command == command
	assert catalog[0].source == "external"
	assert catalog[0].content == ""
	assert rendered == {command: "rendered brief"}
	assert detail is not None
	assert detail.id == command
	assert detail.content == "rendered brief"
	assert detail.source == "external"
	assert missing is None


@pytest.mark.asyncio
async def test_mcp_prompt_render_skips_failed_prompt_fetch(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP prompt rendering skips one failed upstream prompt fetch."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	command = str(server.discovered_prompts[0]["command"])
	monkeypatch.setattr(mcp_prompts, "MCPClient", _FailingPromptClient)

	rendered = await render_external_prompt_content_map(db_session, {command})

	assert rendered == {}


@pytest.mark.asyncio
async def test_mcp_prompt_render_skips_lookup_without_mcp_commands(
	db_session: AsyncSession,
) -> None:
	"""MCP prompt rendering skips metadata lookup when no MCP command is reachable."""
	with patch.object(
		db_session,
		"execute",
		new=AsyncMock(side_effect=AssertionError("unexpected DB read")),
	):
		rendered = await render_external_prompt_content_map(
			db_session,
			{"assistant", "local-subprompt"},
		)

	assert rendered == {}


@pytest.mark.asyncio
async def test_mcp_cache_invalidates_after_server_update(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP cache invalidation refreshes prompt refs after server updates."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	command = str(server.discovered_prompts[0]["command"])
	assert command in await load_external_prompt_placeholders(db_session)
	principal = await _principal(
		db_session,
		frozenset({ActionPermission.MCP_MANAGE}),
	)

	await mcp_service.update_server(
		server.id,
		MCPServerUpdate(name=f"{server.name}-renamed"),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	assert str(server.discovered_prompts[0]["command"]) == command
	assert command in await load_external_prompt_placeholders(db_session)

	await mcp_service.update_server(
		server.id,
		MCPServerUpdate(enabled=False),
		db_session,
		principal=principal,
	)
	await db_session.commit()
	placeholders = await load_external_prompt_placeholders(db_session)
	assert command not in placeholders


@pytest.mark.asyncio
async def test_mcp_list_change_listener_refetches_server_snapshot(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP list-change notifications trigger a debounced server refetch."""
	await invalidate_mcp_cache(db_session)
	server = await _create_discovered_server(db_session, monkeypatch)
	refetched = asyncio.Event()
	refetch_calls: list[str] = []

	async def discover_server_unchecked(
		server: MCPServer,
		session: AsyncSession,
	) -> object:
		refetch_calls.append(str(server.id))
		refetched.set()
		_ = session
		return object()

	monkeypatch.setattr(mcp_listeners, "MCPClient", _ListChangedClient)
	monkeypatch.setattr(
		mcp_listeners,
		"discover_server_unchecked",
		discover_server_unchecked,
	)
	monkeypatch.setattr(
		settings.integrations.mcp,
		"list_change_debounce_seconds",
		0.01,
	)

	task = asyncio.create_task(
		mcp_listeners.listen_for_server_list_changes(str(server.id))
	)
	try:
		await asyncio.wait_for(refetched.wait(), timeout=2.0)
	finally:
		task.cancel()
		with contextlib.suppress(asyncio.CancelledError):
			await task

	assert refetch_calls == [str(server.id)]


@pytest.mark.asyncio
async def test_mcp_server_flows_require_manage_permission(
	db_session: AsyncSession,
) -> None:
	"""MCP server list and create flows require mcp:manage permission."""
	principal = await _principal(db_session, frozenset())

	with pytest.raises(HTTPException) as list_exc:
		await mcp_service.list_servers(db_session, principal=principal)
	assert list_exc.value.status_code == 403

	with pytest.raises(HTTPException) as create_exc:
		await mcp_service.create_server(
			MCPServerCreate(name="blocked", url="https://example.test/mcp"),
			db_session,
			principal=principal,
		)
	assert create_exc.value.status_code == 403


@pytest.mark.asyncio
async def test_user_mcp_server_origin_policy_modes(
	db_session: AsyncSession,
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""user-owned MCP server origins obey allow and deny policy modes."""
	principal = await _principal(
		db_session,
		frozenset({ActionPermission.USER_MCP_MANAGE}),
	)

	monkeypatch.setattr(settings.integrations.mcp, "user_server_origin_mode", "deny")
	monkeypatch.setattr(
		settings.integrations.mcp,
		"user_server_origins",
		["https://blocked.test"],
	)
	with pytest.raises(HTTPException) as denied_exc:
		await mcp_service.create_server(
			MCPServerCreate(
				name="blocked user MCP",
				scope=MCPServerScope.USER,
				url="https://blocked.test/mcp",
			),
			db_session,
			principal=principal,
		)
	assert denied_exc.value.status_code == 400

	allowed_by_deny_mode = await mcp_service.create_server(
		MCPServerCreate(
			name="unblocked user MCP",
			scope=MCPServerScope.USER,
			url="https://allowed.test/mcp",
		),
		db_session,
		principal=principal,
	)
	assert allowed_by_deny_mode.url == "https://allowed.test/mcp"

	monkeypatch.setattr(settings.integrations.mcp, "user_server_origin_mode", "allow")
	monkeypatch.setattr(
		settings.integrations.mcp,
		"user_server_origins",
		["https://allowed.test"],
	)
	with pytest.raises(HTTPException) as not_allowed_exc:
		await mcp_service.create_server(
			MCPServerCreate(
				name="not allowlisted user MCP",
				scope=MCPServerScope.USER,
				url="https://other.test/mcp",
			),
			db_session,
			principal=principal,
		)
	assert not_allowed_exc.value.status_code == 400

	allowed_by_allow_mode = await mcp_service.create_server(
		MCPServerCreate(
			name="allowlisted user MCP",
			scope=MCPServerScope.USER,
			url="https://allowed.test/mcp",
		),
		db_session,
		principal=principal,
	)
	assert allowed_by_allow_mode.url == "https://allowed.test/mcp"
