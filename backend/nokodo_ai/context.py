"""agent execution contexts shared by the SDK runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
	from .chat_models import ChatModel
	from .types import JSONObject


@dataclass(frozen=True, slots=True)
class AgentContext:
	"""read-only context provided to filters, hooks, and tools during execution.

	mutable per-iteration data belongs in ``AgentIterationState``. tool-call
	data belongs in ``ToolCallContext``.

	attributes:
		model: the chat model being used for execution
	"""

	model: ChatModel = field()


@dataclass(frozen=True, slots=True)
class ToolCallContext:
	"""tool-specific context for a single tool invocation.

	attributes:
		tool_call_id: id of the current tool call
		retry_count: number of retries for the tool call
		tool_call_start_time: monotonic timestamp from when the tool call generation
			began. use with time.monotonic() for elapsed time calculations.
		metadata: tool-call metadata from the provider/runtime
	"""

	tool_call_id: str = field()
	tool_call_start_time: float = field()
	retry_count: int = field(default=0)
	metadata: JSONObject = field(default_factory=dict)
