"""agent execution context - runtime state passed to tools and filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING


if TYPE_CHECKING:
	from nokodo_ai import JSONObject
	from nokodo_ai.chat_models import ChatModel
	from nokodo_ai.thread import Thread


@dataclass(slots=True)
class AgentContext:
	"""runtime context provided to tools and filters during agent execution.

	this contains execution state that's always available regardless of the
	application-specific context. it tracks the current thread, model, and
	iteration state.

	attributes:
		thread: the current conversation thread
		model: the chat model being used for execution
		iteration: current agent loop iteration (0-indexed)
		tool_call_id: id of the current tool call (only set during tool execution)
		retry_count: number of retries for the current operation
	"""

	thread: Thread = field()
	model: ChatModel = field()
	tool_call_id: str = field()
	iteration: int = field(default=0)
	retry_count: int = field(default=0)
	metadata: JSONObject = field(default_factory=dict)
