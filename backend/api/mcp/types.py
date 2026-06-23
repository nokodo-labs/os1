"""raw MCP adapter data types."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from nokodo_ai.types.json import JSONObject, JSONValue


type MCPListChangedKind = Literal["tools", "resources", "prompts"]


@dataclass(frozen=True, slots=True)
class MCPToolSpec:
	"""tool exposed by an MCP server."""

	name: str
	description: str
	input_schema: JSONObject


@dataclass(frozen=True, slots=True)
class MCPResourceSpec:
	"""resource exposed by an MCP server."""

	uri: str
	name: str
	description: str
	mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class MCPPromptSpec:
	"""prompt exposed by an MCP server."""

	name: str
	description: str
	arguments: list[JSONObject] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MCPCapabilitySnapshot:
	"""complete discovery snapshot from an MCP server."""

	tools: list[MCPToolSpec] = field(default_factory=list)
	resources: list[MCPResourceSpec] = field(default_factory=list)
	prompts: list[MCPPromptSpec] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MCPToolCallResult:
	"""result returned by an MCP tool call."""

	is_error: bool
	text: str
	structured_content: JSONValue | None = None

	def as_output_text(self) -> str:
		"""return text suitable for a model-visible tool message."""
		if self.structured_content is None:
			return self.text
		return json.dumps(
			{"text": self.text, "structured_content": self.structured_content},
			ensure_ascii=False,
		)


@dataclass(frozen=True, slots=True)
class MCPPromptRenderResult:
	"""result returned by an MCP prompt request."""

	description: str | None
	text: str


@dataclass(frozen=True, slots=True)
class MCPListChangedEvent:
	"""server notification that an MCP capability list changed."""

	kind: MCPListChangedKind


type MCPServerEvent = MCPListChangedEvent
