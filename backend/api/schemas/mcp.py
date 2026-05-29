"""MCP schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from api.models.mcp import (
	MCPAuthType,
	MCPServerScope,
	MCPServerStatus,
	MCPTransport,
)
from api.schemas.common import (
	MISSING,
	MetadataModel,
	MetadataUpdateModel,
	MissingType,
	TimestampedModel,
)
from nokodo_ai.types.json import JSONObject
from nokodo_ai.utils.typeid import TypeID


class MCPSurfaceConfig(BaseModel):
	"""enabled MCP capability families."""

	tools: bool = True
	resources: bool = False
	prompts: bool = False
	sampling: bool = False


class MCPServerBase(MetadataModel):
	"""shared MCP server fields."""

	name: str = Field(min_length=1, max_length=120)
	description: str | None = None
	scope: MCPServerScope = MCPServerScope.GLOBAL
	transport: MCPTransport = MCPTransport.STREAMABLE_HTTP
	url: str | None = Field(default=None, max_length=2048)
	command: str | None = Field(default=None, max_length=1024)
	args: list[str] = Field(default_factory=list)
	env: JSONObject = Field(default_factory=dict)
	auth_type: MCPAuthType = MCPAuthType.NONE
	headers: JSONObject = Field(default_factory=dict)
	enabled: bool = True
	capabilities: MCPSurfaceConfig = Field(default_factory=MCPSurfaceConfig)
	config: JSONObject = Field(default_factory=dict)

	@field_validator("headers", "env")
	@classmethod
	def _coerce_none_object(cls, value: object) -> object:
		if value is None:
			return {}
		return value


class MCPServerCreate(MCPServerBase):
	"""payload for creating an MCP server."""

	access_token: str | None = Field(default=None, max_length=4096)


class MCPServerUpdate(MetadataUpdateModel):
	"""payload for updating an MCP server."""

	name: str | MissingType = MISSING
	description: str | None | MissingType = MISSING
	transport: MCPTransport | MissingType = MISSING
	url: str | None | MissingType = MISSING
	command: str | None | MissingType = MISSING
	args: list[str] | MissingType = MISSING
	env: JSONObject | MissingType = MISSING
	auth_type: MCPAuthType | MissingType = MISSING
	headers: JSONObject | MissingType = MISSING
	access_token: str | None | MissingType = MISSING
	enabled: bool | MissingType = MISSING
	capabilities: MCPSurfaceConfig | MissingType = MISSING
	config: JSONObject | MissingType = MISSING


class MCPPromptArgument(BaseModel):
	"""argument accepted by an MCP prompt."""

	name: str
	description: str | None = None
	required: bool | None = None


class MCPDiscoveredTool(BaseModel):
	"""tool discovered from an MCP server."""

	id: TypeID
	name: str
	normalized_name: str
	description: str = ""
	input_schema: JSONObject = Field(default_factory=dict)
	output_schema: JSONObject | None = None
	enabled: bool = True
	schema_hash: str
	last_discovered_at: datetime | None = None


class MCPDiscoveredResource(BaseModel):
	"""resource discovered from an MCP server."""

	id: TypeID
	uri: str
	name: str
	description: str = ""
	mime_type: str | None = None
	enabled: bool = True
	schema_hash: str
	last_discovered_at: datetime | None = None


class MCPDiscoveredPrompt(BaseModel):
	"""prompt discovered from an MCP server."""

	id: TypeID
	name: str
	command: str
	description: str = ""
	arguments: list[MCPPromptArgument] = Field(default_factory=list)
	enabled: bool = True
	schema_hash: str
	last_discovered_at: datetime | None = None

	@property
	def requires_arguments(self) -> bool:
		"""whether this prompt has required arguments."""
		return any(argument.required is True for argument in self.arguments)


class MCPDiscoveredCapabilities(BaseModel):
	"""latest discovered MCP capability snapshots for one server."""

	tools: list[MCPDiscoveredTool] = Field(default_factory=list)
	resources: list[MCPDiscoveredResource] = Field(default_factory=list)
	prompts: list[MCPDiscoveredPrompt] = Field(default_factory=list)


class MCPServer(MetadataModel, TimestampedModel):
	"""MCP server response."""

	id: TypeID
	name: str
	description: str | None = None
	scope: MCPServerScope
	owner_user_id: TypeID | None = None
	transport: MCPTransport
	url: str | None = None
	auth_type: MCPAuthType
	enabled: bool
	capabilities: MCPSurfaceConfig = Field(default_factory=MCPSurfaceConfig)
	status: MCPServerStatus
	last_discovered_at: datetime | None = None
	last_error: str | None = None
	has_credentials: bool = False
	discovered_tools: list[MCPDiscoveredTool] = Field(default_factory=list)
	discovered_resources: list[MCPDiscoveredResource] = Field(default_factory=list)
	discovered_prompts: list[MCPDiscoveredPrompt] = Field(default_factory=list)


class MCPDiscoveryResult(BaseModel):
	"""MCP discovery response."""

	server: MCPServer
	capabilities: MCPDiscoveredCapabilities
