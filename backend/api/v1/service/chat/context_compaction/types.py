"""shared context compaction types."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from api.models.thread_summary import ThreadSummary
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.typeid import TypeID


type BlockingSummarize = Callable[
	[list[SDKMessage], TypeID | None, TypeID | None], Awaitable[ThreadSummary | None]
]
type ContextCompactionProgressCallback = Callable[[int, str], Awaitable[None]]
type ContextCompactionTier = Literal[
	"raw",
	"t1_tool_io",
	"t2_ready_summary",
	"t3_blocking_summary",
	"t4_prune",
]
type ContextCompactionTriggerReason = Literal["fits", "soft_pressure", "over_budget"]


class ContextCompactionError(RuntimeError):
	"""raised when no valid prompt representation can fit the budget."""


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
	compaction_tier: ContextCompactionTier = "raw"
	trigger_reason: ContextCompactionTriggerReason = "fits"
	effective_context_window: int | None = None
