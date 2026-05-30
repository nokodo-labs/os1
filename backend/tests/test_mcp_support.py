"""unit tests for MCP support helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch

import mcp.types as sdk_types
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.mcp import MCPClient, MCPClientConfig, MCPListChangedEvent
from api.mcp.types import (
	MCPCapabilitySnapshot,
	MCPPromptSpec,
	MCPToolCallResult,
	MCPToolSpec,
)
from api.models.mcp import (
	MCPAuthType,
	MCPServer,
	MCPServerScope,
	MCPServerStatus,
	MCPTransport,
)
from api.models.user import User
from api.schemas.mcp import MCPServer as MCPServerSchema
from api.schemas.mcp import MCPServerCreate
from api.settings import settings
from api.v1.service.auth import Principal
from api.v1.service.chat.context import AppContext
from api.v1.service.integrations.mcp.ids import (
	mcp_server_tools_plugin_id,
	mcp_tool_plugin_id,
	parse_mcp_server_tools_plugin_id,
	parse_mcp_tool_plugin_id,
)
from api.v1.service.integrations.mcp.normalization import (
	normalized_input_schema,
	normalized_mcp_prompt_command,
	normalized_mcp_tool_name,
)
from api.v1.service.integrations.mcp.service import (
	_encrypt_access_token,
	_replace_discovered_snapshot,
	_validate_server_payload,
	call_tool,
	client_config,
	discover_server_unchecked,
	get_available_plugin,
	list_available_plugins,
)
from api.v1.service.integrations.mcp.tools import MCPRemoteTool, resolve_mcp_tools
from api.v1.service.prompts import load_external_prompt_placeholders
from api.v1.service.prompts import runtime as prompt_runtime
from nokodo_ai import AgentContext, AgentIterationSnapshot, AgentIterationState
from nokodo_ai.chat_models import ChatModel
from nokodo_ai.context import ToolCallContext
from nokodo_ai.messages import ToolMessage
from nokodo_ai.threads import Thread
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import new_typeid


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


class _ScalarRows:
	"""small scalar-result stand-in for patched SQLAlchemy execute calls."""

	def __init__(self, rows: list[object]) -> None:
		"""store scalar rows for later result helpers."""
		self._rows = rows

	def all(self) -> list[object]:
		"""return every stored scalar row."""
		return self._rows

	def one_or_none(self) -> object | None:
		"""return the first scalar row or None when empty."""
		return self._rows[0] if self._rows else None


class _QueryRows:
	"""small query-result stand-in for patched SQLAlchemy execute calls."""

	def __init__(self, rows: list[object]) -> None:
		"""store query rows for scalar access."""
		self._rows = rows

	def scalars(self) -> _ScalarRows:
		"""return stored rows through a scalar-result facade."""
		return _ScalarRows(self._rows)


def _app_context() -> AppContext:
	"""create an application context with a superuser principal."""
	user = User(
		id=new_typeid("user"),
		email="mcp-support@example.com",
		username="mcp_support_user",
		hashed_password="x",
		is_superuser=True,
	)
	return AppContext(
		session=AsyncSession(),
		principal=Principal(user=user, group_ids=(), permissions=frozenset()),
		event_emitter=_noop_event_emitter,
	)


def test_mcp_plugin_ids_round_trip() -> None:
	"""MCP dynamic plugin ids round-trip through parser helpers."""
	server_id = str(new_typeid("mcpsrv"))
	tool_snapshot_id = str(new_typeid("mcptool"))

	tool_id = mcp_tool_plugin_id(server_id, tool_snapshot_id)
	server_tools_id = mcp_server_tools_plugin_id(server_id)

	assert parse_mcp_tool_plugin_id(tool_id) == (server_id, tool_snapshot_id)
	assert parse_mcp_server_tools_plugin_id(server_tools_id) == server_id
	assert parse_mcp_tool_plugin_id(server_tools_id) is None
	assert parse_mcp_server_tools_plugin_id(tool_id) is None


def test_normalized_input_schema_repairs_provider_schema_edges() -> None:
	"""MCP schema normalization repairs provider-hostile schema edges."""
	schema: JSONObject = {
		"properties": {"item": {"$ref": "#/definitions/Thing"}},
		"required": ["item", "missing"],
		"definitions": {"Thing": {"type": "object"}},
	}

	normalized = normalized_input_schema(schema)

	assert normalized["type"] == "object"
	assert normalized["required"] == ["item"]
	assert normalized["properties"] == {"item": {"$ref": "#/$defs/Thing"}}
	assert normalized["$defs"] == {"Thing": {"type": "object", "properties": {}}}
	name = normalized_mcp_tool_name("GitHub Search", "repo/list")
	assert name.startswith("mcp_github_search_repo_list_")
	assert len(name) <= 64
	assert normalized_mcp_tool_name("srv", "repo-list") != (
		normalized_mcp_tool_name("srv", "repo_list")
	)
	command = normalized_mcp_prompt_command(
		"mcpsrv_01test",
		"mcpprompt_01brief",
		"repo/list",
	)
	assert command.startswith("mcp-mcpsrv-01test-mcpprompt-01brief-repo-list")
	assert len(command) <= 120


def test_mcp_server_response_redacts_connection_secrets() -> None:
	"""MCP server responses never expose connection secret fields."""
	fields = MCPServerSchema.model_fields

	assert "headers" not in fields
	assert "env" not in fields
	assert "config" not in fields
	assert "command" not in fields
	assert "args" not in fields


def test_mcp_tool_call_result_serializes_structured_content_as_json() -> None:
	"""MCP tool call results include structured content in output text."""
	structured_content: JSONObject = {"items": ["one", "two"]}
	result = MCPToolCallResult(
		is_error=False,
		text="done",
		structured_content=structured_content,
	)

	assert json.loads(result.as_output_text()) == {
		"text": "done",
		"structured_content": {"items": ["one", "two"]},
	}


@pytest.mark.asyncio
async def test_mcp_remote_tool_calls_service_with_json_arguments() -> None:
	"""MCP remote tools forward JSON-safe arguments to the service layer."""
	app_context = _app_context()
	server_id = str(new_typeid("mcpsrv"))
	tool_id = str(new_typeid("mcptool"))
	tool = MCPRemoteTool(
		name="mcp_demo_lookup",
		description="demo lookup",
		parameters={"type": "object", "properties": {}},
		server_id=server_id,
		mcp_tool_id=tool_id,
		mcp_tool_name="lookup",
	)
	structured_content: JSONObject = {"ok": True}
	result = MCPToolCallResult(
		is_error=False,
		text="done",
		structured_content=structured_content,
	)

	try:
		with patch(
			"api.v1.service.integrations.mcp.tools.call_tool",
			new=AsyncMock(return_value=result),
		) as call_tool:
			message = await tool.call(
				_state(),
				_agent_context(),
				_tool_call_context(),
				app_context,
				numbers=(1, 2),
				nested={"enabled": True},
			)
	finally:
		await app_context.session.close()

	assert isinstance(message, ToolMessage)
	assert not message.is_error
	assert json.loads(message.tool_output) == {
		"text": "done",
		"structured_content": {"ok": True},
	}
	call_tool.assert_awaited_once_with(
		server_id,
		tool_id,
		"lookup",
		{"numbers": [1, 2], "nested": {"enabled": True}},
		app_context.session,
		app_context.principal,
	)


@pytest.mark.asyncio
async def test_mcp_plugins_project_from_server_snapshots() -> None:
	"""MCP server snapshots project into dynamic plugin metadata."""
	tool_id = new_typeid("mcptool")
	server = _mcp_server(discovered_tools=[_tool_snapshot(tool_id)])
	session = AsyncSession()
	try:
		with patch.object(
			session,
			"execute",
			new=AsyncMock(return_value=_QueryRows([server])),
		):
			plugins = await list_available_plugins(session)
			server_plugin = await get_available_plugin(
				mcp_server_tools_plugin_id(str(server.id)),
				session,
			)
			tool_plugin = await get_available_plugin(
				mcp_tool_plugin_id(str(server.id), str(tool_id)),
				session,
			)
	finally:
		await session.close()

	plugin_ids = {plugin.id for plugin in plugins}
	assert mcp_server_tools_plugin_id(str(server.id)) in plugin_ids
	assert mcp_tool_plugin_id(str(server.id), str(tool_id)) in plugin_ids
	assert server_plugin is not None
	assert server_plugin.name == "Demo MCP tools"
	assert tool_plugin is not None
	assert tool_plugin.name == "Demo MCP: lookup"


@pytest.mark.asyncio
async def test_resolve_mcp_tools_deduplicates_server_and_tool_ids() -> None:
	"""MCP tool resolution deduplicates selected server and tool ids."""
	tool_id = new_typeid("mcptool")
	server = _mcp_server(discovered_tools=[_tool_snapshot(tool_id)])
	session = AsyncSession()
	try:
		with patch.object(
			session,
			"execute",
			new=AsyncMock(return_value=_QueryRows([server])),
		):
			tools = await resolve_mcp_tools(
				[
					mcp_server_tools_plugin_id(str(server.id)),
					mcp_tool_plugin_id(str(server.id), str(tool_id)),
				],
				session,
			)
	finally:
		await session.close()

	assert len(tools) == 1
	tool = tools[0]
	assert isinstance(tool, MCPRemoteTool)
	assert tool.server_id == str(server.id)
	assert tool.mcp_tool_id == str(tool_id)
	assert tool.mcp_tool_name == "lookup"


@pytest.mark.asyncio
async def test_mcp_prompt_placeholders_skip_required_arguments() -> None:
	"""MCP prompt placeholders exclude prompts that need arguments."""
	ready_prompt = new_typeid("mcpprompt")
	requires_args = new_typeid("mcpprompt")
	server = _mcp_server()
	server.discovered_prompts = [
		_prompt_snapshot(str(server.id), ready_prompt, "brief", required=False),
		_prompt_snapshot(str(server.id), requires_args, "brief-topic", required=True),
	]
	session = AsyncSession()
	try:
		with patch.object(
			session,
			"execute",
			new=AsyncMock(return_value=_QueryRows([server])),
		):
			placeholders = await load_external_prompt_placeholders(session)
	finally:
		await session.close()

	assert placeholders == {
		normalized_mcp_prompt_command(str(server.id), str(ready_prompt), "brief"): "",
	}


@pytest.mark.asyncio
async def test_mcp_discovery_updates_server_status_and_snapshots() -> None:
	"""MCP discovery stores ready status and discovered snapshots."""

	class _DiscoveryClient:
		"""fake MCP client that returns one discovered tool and prompt."""

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
			"""return a snapshot containing one discovered tool and prompt."""
			assert include_resources is False
			assert include_prompts is True
			return MCPCapabilitySnapshot(
				tools=[MCPToolSpec("lookup", "demo lookup", {})],
				prompts=[MCPPromptSpec("brief", "demo prompt", [])],
			)

	server = _mcp_server()
	session = AsyncSession()
	try:
		with (
			patch(
				"api.v1.service.integrations.mcp.service.MCPClient",
				new=_DiscoveryClient,
			),
			patch.object(session, "add") as add,
			patch.object(session, "flush", new=AsyncMock()) as flush,
			patch.object(session, "refresh", new=AsyncMock()) as refresh,
		):
			capabilities = await discover_server_unchecked(server, session)
	finally:
		await session.close()

	assert server.status is MCPServerStatus.READY
	assert server.last_error is None
	assert server.last_discovered_at is not None
	assert capabilities.tools[0].name == "lookup"
	assert capabilities.prompts[0].name == "brief"
	assert server.discovered_tools[0]["name"] == "lookup"
	add.assert_called_once_with(server)
	flush.assert_awaited_once()
	refresh.assert_awaited_once_with(server)


@pytest.mark.asyncio
async def test_mcp_discovery_records_error_status() -> None:
	"""MCP discovery records error status when upstream discovery fails."""

	class _FailingDiscoveryClient:
		"""fake MCP client that raises during discovery."""

		def __init__(self, config: MCPClientConfig) -> None:
			"""store the client config for parity with the real MCP client."""
			self.config = config

		async def __aenter__(self) -> _FailingDiscoveryClient:
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
			"""raise a connection-style failure during fake discovery."""
			raise OSError("mcp offline")

	server = _mcp_server()
	session = AsyncSession()
	try:
		with (
			patch(
				"api.v1.service.integrations.mcp.service.MCPClient",
				new=_FailingDiscoveryClient,
			),
			patch.object(session, "add") as add,
			patch.object(session, "flush", new=AsyncMock()) as flush,
			patch.object(session, "refresh", new=AsyncMock()) as refresh,
		):
			with pytest.raises(OSError, match="mcp offline"):
				await discover_server_unchecked(server, session)
	finally:
		await session.close()

	assert server.status is MCPServerStatus.ERROR
	assert server.last_error == "mcp offline"
	add.assert_called_once_with(server)
	flush.assert_awaited_once()
	refresh.assert_awaited_once_with(server)


def test_mcp_client_config_adds_bearer_auth_and_clamps_timeout() -> None:
	"""MCP client config adds bearer auth and clamps unsafe timeouts."""
	server = _mcp_server(
		auth_type=MCPAuthType.BEARER,
		headers={"X-Demo": "ok", "ignored": 3},
		encrypted_access_token=_encrypt_access_token("secret-token"),
		config={"timeout": 999999},
	)

	config = client_config(server)

	assert config.headers == {
		"X-Demo": "ok",
		"Authorization": "Bearer secret-token",
	}
	assert config.timeout == float(settings.integrations.mcp.max_timeout_seconds)


def test_mcp_server_payload_validation_rejects_invalid_streamable_http() -> None:
	"""MCP streamable HTTP validation rejects incompatible payload fields."""
	with pytest.raises(HTTPException, match="streamable HTTP MCP requires a URL"):
		_validate_server_payload(MCPServerCreate(name="missing url"))

	with pytest.raises(
		HTTPException,
		match="streamable HTTP MCP does not support command",
	):
		_validate_server_payload(
			MCPServerCreate(
				name="bad command",
				url="https://example.test/mcp",
				command="mcp-server",
			)
		)


@pytest.mark.asyncio
async def test_mcp_call_tool_rejects_snapshot_name_mismatch() -> None:
	"""MCP tool calls reject stale plugin ids with renamed snapshots."""
	tool_id = new_typeid("mcptool")
	server = _mcp_server(discovered_tools=[_tool_snapshot(tool_id)])
	session = AsyncSession()
	try:
		with patch.object(
			session,
			"execute",
			new=AsyncMock(return_value=_QueryRows([server])),
		):
			with pytest.raises(HTTPException) as exc:
				await call_tool(
					str(server.id),
					str(tool_id),
					"renamed-elsewhere",
					{},
					session,
				)
	finally:
		await session.close()

	assert exc.value.status_code == 404
	assert exc.value.detail == "MCP tool not found"


@pytest.mark.asyncio
async def test_prompt_runtime_expands_referenced_mcp_prompt(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""prompt runtime expands referenced MCP prompt include commands."""

	class _PromptRows:
		"""empty prompt row facade for local prompt lookup."""

		def all(self) -> list[tuple[str, str]]:
			"""return no local prompt rows."""
			return []

	async def render_mcp_prompts(
		_session: AsyncSession,
		commands: set[str],
	) -> dict[str, str]:
		"""return rendered content for the referenced fake MCP prompt."""
		assert "mcp-demo-brief" in commands
		return {"mcp-demo-brief": "remote brief"}

	session = AsyncSession()
	try:
		with patch.object(
			session,
			"execute",
			new=AsyncMock(return_value=_PromptRows()),
		):
			monkeypatch.setattr(
				prompt_runtime,
				"render_external_prompt_content_map",
				render_mcp_prompts,
			)
			rendered = await prompt_runtime.render_inline_with_prompts(
				session,
				"local {% include 'mcp-demo-brief' %}",
			)
	finally:
		await session.close()

	assert rendered == "local remote brief"


def test_mcp_discovery_snapshot_preserves_embedded_ids() -> None:
	"""MCP discovery preserves embedded snapshot ids across refreshes."""
	server = _mcp_server()
	first = _replace_discovered_snapshot(
		server,
		MCPCapabilitySnapshot(
			tools=[
				MCPToolSpec(
					name="lookup",
					description="look up data",
					input_schema={"type": "object"},
				)
			],
			prompts=[
				MCPPromptSpec(
					name="brief",
					description="write a brief",
					arguments=[],
				)
			],
		),
	)
	second = _replace_discovered_snapshot(
		server,
		MCPCapabilitySnapshot(
			tools=[
				MCPToolSpec(
					name="lookup",
					description="look up newer data",
					input_schema={"properties": {}},
				)
			],
			prompts=[
				MCPPromptSpec(
					name="brief",
					description="write a better brief",
					arguments=[],
				)
			],
		),
	)

	assert second.tools[0].id == first.tools[0].id
	assert second.prompts[0].id == first.prompts[0].id
	assert server.discovered_tools[0]["id"] == str(first.tools[0].id)
	assert server.discovered_prompts[0]["id"] == str(first.prompts[0].id)


def test_mcp_discovery_snapshot_rejects_duplicate_remote_names() -> None:
	"""MCP discovery rejects duplicate remote capability names."""
	server = _mcp_server()
	with pytest.raises(ValueError, match="duplicate tool"):
		_replace_discovered_snapshot(
			server,
			MCPCapabilitySnapshot(
				tools=[
					MCPToolSpec(name="lookup", description="one", input_schema={}),
					MCPToolSpec(name="lookup", description="two", input_schema={}),
				]
			),
		)


@pytest.mark.asyncio
async def test_mcp_client_streams_normalized_list_changed_events(
	monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""MCP client exposes SDK list-change notifications as adapter events."""
	type CapturedHandler = Callable[[object], Awaitable[None]]

	class _Transport:
		"""fake streamable HTTP transport context manager."""

		async def __aenter__(self) -> tuple[object, object, object]:
			return object(), object(), object()

		async def __aexit__(
			self,
			exc_type: object,
			exc: object,
			tb: object,
		) -> None:
			return None

	class _Session:
		"""fake MCP session that captures the private SDK message handler."""

		captured_message_handler: CapturedHandler | None = None

		def __init__(
			self,
			read_stream: object,
			write_stream: object,
			message_handler: CapturedHandler | None = None,
		) -> None:
			_ = read_stream, write_stream
			_Session.captured_message_handler = message_handler

		async def __aenter__(self) -> _Session:
			return self

		async def __aexit__(
			self,
			exc_type: object,
			exc: object,
			tb: object,
		) -> None:
			return None

		async def initialize(self) -> object:
			return object()

	def streamable_http_client(
		url: str,
		**kwargs: object,
	) -> _Transport:
		assert url == "https://example.test/mcp"
		assert kwargs["terminate_on_close"] is False
		return _Transport()

	monkeypatch.setattr("api.mcp.client.streamablehttp_client", streamable_http_client)
	monkeypatch.setattr("api.mcp.client.ClientSession", _Session)

	client = MCPClient(
		MCPClientConfig(url="https://example.test/mcp"),
		receive_events=True,
	)
	await client.connect()

	handler = _Session.captured_message_handler
	assert handler is not None
	await handler(sdk_types.ServerNotification(sdk_types.ToolListChangedNotification()))
	event = await asyncio.wait_for(anext(client.events()), timeout=1.0)
	await client.disconnect()

	assert event == MCPListChangedEvent(kind="tools")


@pytest.mark.asyncio
async def test_mcp_client_get_prompt_flattens_text_messages() -> None:
	"""MCP client prompt rendering flattens text messages with spacing."""

	class _Content:
		"""fake prompt message content carrying text."""

		def __init__(self, text: str) -> None:
			"""store fake prompt message text."""
			self.text = text

	class _Message:
		"""fake prompt message containing text content."""

		def __init__(self, text: str) -> None:
			"""wrap fake text content in a message object."""
			self.content = _Content(text)

	class _PromptResult:
		"""fake MCP prompt result returned by the fake session."""

		description = "demo prompt"
		messages = [_Message("first"), _Message("second")]

	class _Session:
		"""fake raw MCP session for prompt rendering."""

		async def initialize(self) -> object:
			"""return a placeholder initialization result."""
			return object()

		async def list_tools(self) -> object:
			"""return a placeholder tool listing result."""
			return object()

		async def list_resources(self) -> object:
			"""return a placeholder resource listing result."""
			return object()

		async def list_prompts(self) -> object:
			"""return a placeholder prompt listing result."""
			return object()

		async def call_tool(self, name: str, arguments: JSONObject) -> object:
			"""return a placeholder tool call result."""
			return object()

		async def get_prompt(
			self,
			name: str,
			arguments: dict[str, str] | None = None,
		) -> object:
			"""return the fake prompt result for the expected prompt name."""
			assert name == "brief"
			assert arguments is None
			return _PromptResult()

	client = MCPClient(MCPClientConfig())
	client._session = _Session()

	result = await client.get_prompt("brief")

	assert result.description == "demo prompt"
	assert result.text == "first\n\nsecond"


def _mcp_server(
	discovered_tools: list[JSONObject] | None = None,
	discovered_prompts: list[JSONObject] | None = None,
	auth_type: MCPAuthType = MCPAuthType.NONE,
	headers: JSONObject | None = None,
	encrypted_access_token: str | None = None,
	config: JSONObject | None = None,
) -> MCPServer:
	"""build an MCP server model for service-level tests."""
	return MCPServer(
		id=new_typeid("mcpsrv"),
		name="Demo MCP",
		description=None,
		scope=MCPServerScope.GLOBAL,
		transport=MCPTransport.STREAMABLE_HTTP,
		url="https://example.test/mcp",
		command=None,
		args=[],
		env={},
		auth_type=auth_type,
		headers=headers or {},
		encrypted_access_token=encrypted_access_token,
		enabled=True,
		capabilities={"tools": True, "resources": False, "prompts": True},
		config=config or {},
		status=MCPServerStatus.DISCONNECTED,
		discovered_tools=discovered_tools or [],
		discovered_resources=[],
		discovered_prompts=discovered_prompts or [],
		metadata_={},
	)


def _tool_snapshot(tool_id: str) -> JSONObject:
	"""build a discovered MCP tool snapshot for service tests."""
	return {
		"id": str(tool_id),
		"name": "lookup",
		"normalized_name": "mcp_demo_lookup",
		"description": "demo lookup",
		"input_schema": {"type": "object", "properties": {}},
		"output_schema": None,
		"enabled": True,
		"schema_hash": "tool-hash",
	}


def _prompt_snapshot(
	server_id: str,
	prompt_id: str,
	name: str,
	required: bool,
) -> JSONObject:
	"""build a discovered MCP prompt snapshot for service tests."""
	return {
		"id": str(prompt_id),
		"name": name,
		"command": normalized_mcp_prompt_command(server_id, str(prompt_id), name),
		"description": "demo prompt",
		"arguments": [{"name": "topic", "description": "topic", "required": required}],
		"enabled": True,
		"schema_hash": "prompt-hash",
	}
