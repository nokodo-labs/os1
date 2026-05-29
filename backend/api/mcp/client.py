"""raw MCP client adapter."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

import mcp.types as sdk_types
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.session import RequestResponder
from pydantic_core import to_jsonable_python

from api.mcp.errors import MCPUnsupportedTransportError
from api.mcp.types import (
	MCPCapabilitySnapshot,
	MCPListChangedEvent,
	MCPPromptRenderResult,
	MCPPromptSpec,
	MCPResourceSpec,
	MCPServerEvent,
	MCPToolCallResult,
	MCPToolSpec,
)
from api.models.mcp import MCPTransport
from nokodo_ai.types.json import JSONObject, JSONValue


type _SDKServerMessage = (
	RequestResponder[sdk_types.ServerRequest, sdk_types.ClientResult]
	| sdk_types.ServerNotification
	| Exception
)


class _ClientSession(Protocol):
	"""subset of the official MCP client session used by this adapter."""

	async def initialize(self) -> object: ...
	async def list_tools(self) -> object: ...
	async def list_resources(self) -> object: ...
	async def list_prompts(self) -> object: ...
	async def call_tool(self, name: str, arguments: JSONObject) -> object: ...
	async def get_prompt(
		self, name: str, arguments: dict[str, str] | None = None
	) -> object: ...


@dataclass(frozen=True, slots=True)
class MCPClientConfig:
	"""connection config for the raw MCP adapter."""

	transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
	url: str | None = None
	headers: dict[str, str] = field(default_factory=dict)
	timeout: float = 30.0


class MCPClient:
	"""small async wrapper around the official MCP client."""

	def __init__(
		self,
		config: MCPClientConfig,
		receive_events: bool = False,
	) -> None:
		"""create a client wrapper for one MCP server connection."""
		self.config = config
		self._events: asyncio.Queue[MCPServerEvent | Exception] | None = (
			asyncio.Queue() if receive_events else None
		)
		self._exit_stack = AsyncExitStack()
		self._session: _ClientSession | None = None

	async def __aenter__(self) -> MCPClient:
		"""connect and return the ready MCP client."""
		await self.connect()
		return self

	async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
		"""disconnect the MCP client when leaving its context."""
		await self.disconnect()

	async def connect(self) -> None:
		"""open the configured MCP transport and initialize a client session."""
		if self.config.transport is not MCPTransport.STREAMABLE_HTTP:
			raise MCPUnsupportedTransportError(
				f"MCP transport is not supported yet: {self.config.transport}"
			)
		if not self.config.url:
			raise MCPUnsupportedTransportError("streamable HTTP MCP requires a URL")

		timeout = timedelta(seconds=self.config.timeout)
		try:
			transport_manager = streamablehttp_client(
				self.config.url,
				headers=self.config.headers or None,
				timeout=timeout,
				terminate_on_close=False,
			)
		except TypeError:
			try:
				transport_manager = streamablehttp_client(
					self.config.url,
					headers=self.config.headers or None,
					timeout=timeout,
				)
			except TypeError:
				transport_manager = streamablehttp_client(
					self.config.url,
					headers=self.config.headers or None,
				)

		try:
			read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
				transport_manager
			)
			session_args = (read_stream, write_stream)
			if self._events is None:
				session_manager = ClientSession(*session_args)
			else:
				session_manager = ClientSession(
					*session_args,
					message_handler=self._handle_sdk_message,
				)
			session: _ClientSession = await self._exit_stack.enter_async_context(
				session_manager
			)
			async with asyncio.timeout(self.config.timeout):
				await session.initialize()
			self._session = session
		except Exception:
			await self.disconnect()
			raise

	async def disconnect(self) -> None:
		"""close the current MCP session."""
		self._session = None
		await self._exit_stack.aclose()

	async def events(self) -> AsyncIterator[MCPServerEvent]:
		"""yield normalized server events from the open MCP session."""
		if self._events is None:
			raise MCPUnsupportedTransportError("MCP event reception is not enabled")
		while True:
			item = await self._events.get()
			if isinstance(item, Exception):
				raise item
			yield item

	async def discover(
		self,
		include_resources: bool,
		include_prompts: bool,
	) -> MCPCapabilitySnapshot:
		"""list enabled capability families from the server."""
		self._require_session()
		tools = await self.list_tools()
		resources = await self.list_resources() if include_resources else []
		prompts = await self.list_prompts() if include_prompts else []
		return MCPCapabilitySnapshot(tools=tools, resources=resources, prompts=prompts)

	async def list_tools(self) -> list[MCPToolSpec]:
		"""list tools exposed by the connected MCP server."""
		session = self._require_session()
		result = await session.list_tools()
		tools = _sequence_attr(result, "tools")
		return [_tool_spec(tool) for tool in tools]

	async def list_resources(self) -> list[MCPResourceSpec]:
		"""list resources exposed by the connected MCP server."""
		session = self._require_session()
		result = await session.list_resources()
		resources = _sequence_attr(result, "resources")
		return [_resource_spec(resource) for resource in resources]

	async def list_prompts(self) -> list[MCPPromptSpec]:
		"""list prompts exposed by the connected MCP server."""
		session = self._require_session()
		result = await session.list_prompts()
		prompts = _sequence_attr(result, "prompts")
		return [_prompt_spec(prompt) for prompt in prompts]

	async def call_tool(self, name: str, arguments: JSONObject) -> MCPToolCallResult:
		"""call an MCP tool."""
		session = self._require_session()
		result = await session.call_tool(name, arguments=arguments)
		content_blocks = _sequence_attr(result, "content")
		parts: list[str] = []
		for block in content_blocks:
			text = _string_attr(block, "text")
			if text:
				parts.append(text)
		structured_content: JSONValue = to_jsonable_python(
			getattr(result, "structuredContent", None),
			exclude_none=True,
			fallback=str,
		)
		return MCPToolCallResult(
			is_error=bool(getattr(result, "isError", False)),
			text="\n".join(parts),
			structured_content=structured_content,
		)

	async def get_prompt(
		self,
		name: str,
		arguments: dict[str, str] | None = None,
	) -> MCPPromptRenderResult:
		"""get an MCP prompt as plain text."""
		session = self._require_session()
		result = await session.get_prompt(name, arguments=arguments)
		parts: list[str] = []
		for message in _sequence_attr(result, "messages"):
			content = getattr(message, "content", None)
			text = _string_attr(content, "text")
			if text:
				parts.append(text)
		return MCPPromptRenderResult(
			description=_string_attr(result, "description"),
			text="\n\n".join(parts),
		)

	def _require_session(self) -> _ClientSession:
		"""return the active SDK session or raise when disconnected."""
		if self._session is None:
			raise MCPUnsupportedTransportError("MCP client is not connected")
		return self._session

	async def _handle_sdk_message(
		self,
		message: _SDKServerMessage,
	) -> None:
		"""enqueue normalized adapter events from SDK server messages."""
		if self._events is None:
			return
		item = _event_from_sdk_message(message)
		if item is not None:
			self._events.put_nowait(item)


def _event_from_sdk_message(
	message: _SDKServerMessage,
) -> MCPServerEvent | Exception | None:
	"""convert one SDK message into an event-stream queue item."""
	if isinstance(message, Exception):
		return message
	if not isinstance(message, sdk_types.ServerNotification):
		return None
	match message.root:
		case sdk_types.ToolListChangedNotification():
			return MCPListChangedEvent(kind="tools")
		case sdk_types.ResourceListChangedNotification():
			return MCPListChangedEvent(kind="resources")
		case sdk_types.PromptListChangedNotification():
			return MCPListChangedEvent(kind="prompts")
		case _:
			return None


def _tool_spec(tool: object) -> MCPToolSpec:
	"""normalize an SDK tool object into an adapter tool spec."""
	return MCPToolSpec(
		name=_required_string_attr(tool, "name"),
		description=_string_attr(tool, "description") or "",
		input_schema=_json_object_from_value(getattr(tool, "inputSchema", None)),
	)


def _resource_spec(resource: object) -> MCPResourceSpec:
	"""normalize an SDK resource object into an adapter resource spec."""
	return MCPResourceSpec(
		uri=_required_string_attr(resource, "uri"),
		name=_string_attr(resource, "name") or _required_string_attr(resource, "uri"),
		description=_string_attr(resource, "description") or "",
		mime_type=_string_attr(resource, "mimeType"),
	)


def _prompt_spec(prompt: object) -> MCPPromptSpec:
	"""normalize an SDK prompt object into an adapter prompt spec."""
	arguments = []
	for argument in _sequence_attr(prompt, "arguments"):
		arguments.append(_json_object_from_value(argument))
	return MCPPromptSpec(
		name=_required_string_attr(prompt, "name"),
		description=_string_attr(prompt, "description") or "",
		arguments=arguments,
	)


def _required_string_attr(value: object, name: str) -> str:
	"""read a required string-ish SDK attribute or raise an adapter error."""
	text = _string_attr(value, name)
	if not text:
		raise MCPUnsupportedTransportError(f"MCP object is missing {name}")
	return text


def _string_attr(value: object, name: str) -> str | None:
	"""read an optional SDK attribute as a string."""
	attr = getattr(value, name, None)
	if attr is None:
		return None
	return str(attr)


def _sequence_attr(value: object, name: str) -> list[object]:
	"""read an SDK list/tuple attribute as a plain list."""
	attr = getattr(value, name, None)
	if attr is None:
		return []
	if isinstance(attr, list):
		return list(attr)
	if isinstance(attr, tuple):
		return list(attr)
	return []


def _json_object_from_value(value: object) -> JSONObject:
	"""normalize an SDK value into a JSON object when possible."""
	json_value = to_jsonable_python(value, exclude_none=True, fallback=str)
	if isinstance(json_value, dict):
		return json_value
	return {}
