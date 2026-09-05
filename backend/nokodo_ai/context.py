"""agent execution contexts shared by the SDK runtime."""

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
	"""

	model: ChatModel = field()
	"""the chat model this run executes against."""


@dataclass(frozen=True, slots=True)
class ToolCallContext:
	"""tool-specific context for a single tool invocation."""

	tool_call_id: str = field()
	"""identifies this call, and correlates the events it emits."""
	tool_call_start_time: float = field()
	"""monotonic start of the call; subtract from ``time.monotonic()``."""
	retry_count: int = field(default=0)
	"""how many times this call has already been attempted."""
	metadata: JSONObject = field(default_factory=dict)
	"""tool-call metadata from the provider or runtime."""
