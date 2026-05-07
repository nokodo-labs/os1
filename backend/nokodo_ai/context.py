"""agent execution context - runtime state passed to tools, filters, and hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
	from .chat_models import ChatModel
	from .threads import Thread
	from .types import JSONObject


@dataclass(slots=True)
class AgentContext:
	"""runtime context provided to tools, filters, and hooks during execution.

	this contains execution state that's always available regardless of the
	application-specific context. it tracks the current thread, model, and
	iteration state.

	attributes:
		thread: the current conversation thread
		model: the chat model being used for execution
		iteration: current agent loop iteration (0-indexed)
		tool_call_id: id of the current tool call, only during tool execution
		retry_count: number of retries for the current operation
		tool_call_start_time: monotonic timestamp from when the tool call generation
			began, only during tool execution. use with time.monotonic() for elapsed
			time calculations when present.
	"""

	thread: Thread = field()
	model: ChatModel = field()
	tool_call_id: str | None = field(default=None)
	iteration: int = field(default=0)
	retry_count: int = field(default=0)
	tool_call_start_time: float | None = field(default=None)
	metadata: JSONObject = field(default_factory=dict)
