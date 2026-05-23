"""shared context compaction types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from api.models.thread_summary import ThreadSummary
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


type BlockingSummarize = Callable[
	[list[SDKMessage], TypeID | None, TypeID | None], Awaitable[ThreadSummary | None]
]
type ContextCompactionProgressCallback = Callable[[int, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ContextCompactionResult:
	"""result of applying context compaction to a thread."""

	thread: SDKThread
	needs_summarization: bool = False
	summarize_messages: list[SDKMessage] = field(default_factory=list)
	start_message_id: TypeID | None = None
	end_message_id: TypeID | None = None
	dropped_count: int = 0
	total_tokens: int = 0
	budget_tokens: int = 0
	summary_count: int = 0
	compacted_tool_call_count: int = 0
	compacted_tool_result_count: int = 0
	compacted_tool_run_count: int = 0
	blocking_summary_count: int = 0
