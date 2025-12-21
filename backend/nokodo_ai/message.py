"""message domain models for SDK execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
	"""a tool call requested by the assistant."""

	id: str
	name: str
	arguments: str


@dataclass
class ToolResult:
	"""result of a tool call execution."""

	tool_call_id: str
	content: str
	is_error: bool = False


@dataclass
class UserMessage:
	"""a message from the user."""

	content: str


@dataclass
class AssistantMessage:
	"""a message from the assistant."""

	content: str
	tool_calls: list[ToolCall] | None = None


@dataclass
class ToolMessage:
	"""a message containing tool execution results."""

	tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class SystemMessage:
	"""a system prompt message."""

	content: str


# union type for all message types
Message = UserMessage | AssistantMessage | ToolMessage | SystemMessage
