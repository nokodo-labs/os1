"""context windowing - token-aware message window management.

applies windowing to an SDK thread after system instructions are injected.
handles summary injection, summarized message exclusion, hard truncation,
and signals when new summarization is needed.

also provides a Layer 2 combined tool result budget guard that can
run on every agent iteration to keep tool outputs within budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from api.models.thread_summary import ThreadSummary
from api.settings.settings import settings as app_settings
from api.v1.service import thread_summaries as summary_service
from api.v1.service.prompt_runtime import SENTINEL_CHAT_WINDOW_INFO
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import SystemMessage as SDKSystemMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.token_estimation import estimate_message_tokens
from nokodo_ai.utils.tokens import compute_available_budget
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

# notice substituted when a tool result is compacted by the Layer 2 guard
_COMPACTED_NOTICE = "[compacted: tool output removed to free context]"


@dataclass(frozen=True, slots=True)
class WindowingResult:
	"""result of applying context windowing to a thread."""

	thread: SDKThread
	needs_summarization: bool = False
	# messages to summarize (oldest unsummarized batch)
	summarize_messages: list[SDKMessage] = field(default_factory=list)
	start_message_id: TypeID | None = None
	end_message_id: TypeID | None = None
	# stats
	dropped_count: int = 0
	total_tokens: int = 0
	budget_tokens: int = 0


def _get_message_id(msg: SDKMessage) -> str | None:
	"""extract the ORM message ID from SDK message metadata."""
	meta = msg.metadata
	if meta and "message_id" in meta:
		return str(meta["message_id"])
	return None


def _find_summarized_cutoff(
	summaries: list[ThreadSummary],
	branch_ids: list[str | None],
) -> int:
	"""find the index in the branch where summarized messages end.

	returns the index of the first unsummarized message (0 if none).
	"""
	if not summaries:
		return 0

	# collect all end_message_ids from active summaries
	end_ids: set[str] = set()
	for s in summaries:
		if s.end_message_id:
			end_ids.add(str(s.end_message_id))

	if not end_ids:
		return 0

	# find the furthest end position in the branch
	max_cutoff = 0
	for i, mid in enumerate(branch_ids):
		if mid and mid in end_ids:
			max_cutoff = max(max_cutoff, i + 1)

	return max_cutoff


def _build_summary_injection(summaries: list[ThreadSummary]) -> str:
	"""build the summary text to inject into the system message."""
	if not summaries:
		return ""

	parts: list[str] = []
	for s in summaries:
		if s.content:
			parts.append(s.content)

	if not parts:
		return ""

	combined = "\n---\n".join(parts)
	return (
		"\n\n## conversation history summary\n\n"
		"the following is a summary of earlier messages in this conversation "
		"that have been compressed to save context space:\n\n"
		f"{combined}"
	)


def _inject_summary_into_system(
	messages: list[SDKMessage],
	summary_text: str,
) -> list[SDKMessage]:
	"""append summary text to the system message."""
	if not summary_text:
		return messages

	result = list(messages)
	for i, msg in enumerate(result):
		if isinstance(msg, SDKSystemMessage):
			existing = msg.text or ""
			new_text = existing + summary_text
			result[i] = SDKSystemMessage.from_text(new_text)
			return result

	# no system message found - prepend one with just the summary
	result.insert(0, SDKSystemMessage.from_text(summary_text.strip()))
	return result


def _build_window_info(
	*,
	summary_count: int,
	dropped_count: int,
	total_tokens: int,
	budget_tokens: int,
	original_message_count: int,
	visible_message_count: int,
) -> str:
	"""build concise windowing state info for the model."""
	parts: list[str] = []

	if summary_count > 0:
		parts.append(
			f"{summary_count} summary/summaries of earlier messages are included above"
		)

	summarized_or_dropped = original_message_count - visible_message_count
	if summarized_or_dropped > 0:
		parts.append(
			f"{summarized_or_dropped} earlier messages have been summarized or trimmed"
		)

	if dropped_count > 0:
		parts.append(
			f"{dropped_count} messages were hard-truncated to fit the context window"
		)

	parts.append(f"you are seeing {visible_message_count} recent messages")

	if budget_tokens > 0:
		usage_pct = int(total_tokens / budget_tokens * 100)
		parts.append(f"context usage: ~{usage_pct}% of available budget")

	return "[context window info: " + "; ".join(parts) + "]"


def _replace_chat_window_sentinel(
	messages: list[SDKMessage],
	window_info: str,
) -> list[SDKMessage]:
	"""replace <<FILTER:chat_window_info>> sentinel in system messages."""
	result = list(messages)
	for i, msg in enumerate(result):
		if isinstance(msg, SDKSystemMessage):
			text = msg.text or ""
			if SENTINEL_CHAT_WINDOW_INFO in text:
				new_text = text.replace(SENTINEL_CHAT_WINDOW_INFO, window_info)
				result[i] = SDKSystemMessage.from_text(new_text)
	return result


async def apply_context_windowing(
	thread: SDKThread,
	*,
	context_window: int | None,
	thread_id: TypeID,
	session: AsyncSession,
) -> WindowingResult:
	"""apply token-aware context windowing to a thread.

	this function:
	1. loads active summaries and removes summarized messages
	2. injects summary content into the system message
	3. applies max_messages cap
	4. hard-truncates if token usage exceeds hard_ratio
	5. signals if new summarization should be scheduled

	call this after inject_system_instructions and before agent.run().
	"""
	ws = app_settings.ai.windowing

	if not ws.enabled:
		# clear the sentinel even when windowing is disabled
		cleared = _replace_chat_window_sentinel(list(thread.messages), "")
		return WindowingResult(
			thread=thread.model_copy(update={"messages": cleared}),
		)

	messages = list(thread.messages)
	branch_ids = [_get_message_id(m) for m in messages]

	# -- step 1: load summaries + exclude summarized messages --

	summaries = await summary_service.list_active_summaries(thread_id, session)
	cutoff = _find_summarized_cutoff(summaries, branch_ids)

	# separate system message (index 0 typically) from conversation messages.
	# system message is never dropped by windowing.
	system_msgs: list[SDKMessage] = []
	conversation_msgs: list[SDKMessage] = []
	conversation_ids: list[str | None] = []

	for i, msg in enumerate(messages):
		if isinstance(msg, SDKSystemMessage):
			system_msgs.append(msg)
		else:
			conversation_msgs.append(msg)
			conversation_ids.append(branch_ids[i])

	# apply cutoff to conversation messages only
	# cutoff is relative to the original branch (including system messages).
	# adjust for the system message offset.
	system_count = len(system_msgs)
	adj_cutoff = max(cutoff - system_count, 0)
	unsummarized = conversation_msgs[adj_cutoff:]
	unsummarized_ids = conversation_ids[adj_cutoff:]

	# -- step 2: inject summary content --

	summary_text = _build_summary_injection(summaries)
	windowed_system = _inject_summary_into_system(system_msgs, summary_text)

	# -- step 3: compute budget --
	# system_tokens is computed from windowed_system which already includes
	# the injected summary text. do NOT pass summary_tokens separately or
	# it will be subtracted twice from the budget.

	system_tokens = sum(estimate_message_tokens(m) for m in windowed_system)
	budget = compute_available_budget(
		context_window,
		system_prompt_tokens=system_tokens,
		response_headroom=ws.response_headroom,
	)

	# -- step 4: apply max_messages cap --

	dropped_count = 0
	if len(unsummarized) > ws.max_messages:
		excess = len(unsummarized) - ws.max_messages
		unsummarized = unsummarized[excess:]
		unsummarized_ids = unsummarized_ids[excess:]
		dropped_count += excess

	# -- step 5: hard truncation if over budget --

	hard_limit = int(budget * ws.hard_ratio)
	total_tokens = sum(estimate_message_tokens(m) for m in unsummarized)

	while total_tokens > hard_limit and len(unsummarized) > 1:
		# drop the oldest non-system message
		removed = unsummarized.pop(0)
		unsummarized_ids.pop(0)
		total_tokens -= estimate_message_tokens(removed)
		dropped_count += 1

	# -- step 6: check if summarization is needed --

	trigger_limit = int(budget * ws.trigger_ratio)
	needs_summarization = total_tokens > trigger_limit and len(unsummarized) > 1

	# identify the batch to summarize (oldest N messages)
	summarize_messages: list[SDKMessage] = []
	start_message_id: TypeID | None = None
	end_message_id: TypeID | None = None

	if needs_summarization:
		batch_size = min(ws.summary_batch_size, len(unsummarized) - 1)
		summarize_messages = unsummarized[:batch_size]
		batch_ids = unsummarized_ids[:batch_size]

		# find first and last message IDs in the batch
		first_id = next((mid for mid in batch_ids if mid), None)
		last_id = next((mid for mid in reversed(batch_ids) if mid), None)
		start_message_id = TypeID(first_id) if first_id else None
		end_message_id = TypeID(last_id) if last_id else None

	# -- step 7: reassemble the thread --

	final_messages = windowed_system + unsummarized

	# inject a notice if messages were dropped by hard truncation
	if dropped_count > 0 and not summary_text:
		notice = SDKSystemMessage.from_text(
			f"[{dropped_count} earlier messages not shown]"
		)
		# insert after system message(s), before conversation
		insert_pos = len(windowed_system)
		final_messages.insert(insert_pos, notice)

	# -- step 8: replace chat_window_info sentinel --

	original_conv_count = len(conversation_msgs)
	visible_conv_count = len(unsummarized)
	window_info = _build_window_info(
		summary_count=len(summaries),
		dropped_count=dropped_count,
		total_tokens=total_tokens,
		budget_tokens=budget,
		original_message_count=original_conv_count,
		visible_message_count=visible_conv_count,
	)
	final_messages = _replace_chat_window_sentinel(final_messages, window_info)

	windowed_thread = thread.model_copy(update={"messages": final_messages})

	if dropped_count > 0 or summaries:
		logger.info(
			"context windowing: %d summaries injected, %d messages dropped, "
			"%d/%d tokens used, summarization_needed=%s",
			len(summaries),
			dropped_count,
			total_tokens,
			budget,
			needs_summarization,
		)

	return WindowingResult(
		thread=windowed_thread,
		needs_summarization=needs_summarization,
		summarize_messages=summarize_messages,
		start_message_id=start_message_id,
		end_message_id=end_message_id,
		dropped_count=dropped_count,
		total_tokens=total_tokens,
		budget_tokens=budget,
	)


def enforce_combined_tool_budget(
	thread: SDKThread,
	*,
	context_window: int | None,
) -> SDKThread:
	"""enforce a combined token budget across all tool results (Layer 2).

	if total tool result tokens exceed `tool_results_combined_max_share`
	of the available context budget, replace the oldest tool results
	with compaction notices until within budget.

	this is designed to run on EVERY agent iteration (via a filter),
	catching cases where multiple tool calls accumulate and collectively
	overflow the context even though each individual result passed
	the per-result truncation (Layer 1).

	inspired by OpenClaw's `enforceToolResultContextBudgetInPlace`.
	"""
	ws = app_settings.ai.windowing
	# budget here intentionally ignores system/summary overhead since
	# those values are not available at this call site. the slight
	# overestimate (~5-10%) is harmless because apply_context_windowing's
	# hard_ratio truncation provides the authoritative backstop.
	budget = compute_available_budget(
		context_window,
		response_headroom=ws.response_headroom,
	)
	combined_limit = int(budget * ws.tool_results_combined_max_share)

	# collect tool message indices and their estimated token costs,
	# ordered by position (oldest first)
	tool_entries: list[tuple[int, int]] = []
	for i, msg in enumerate(thread.messages):
		if isinstance(msg, SDKToolMessage) and msg.tool_output:
			tokens = estimate_message_tokens(msg)
			tool_entries.append((i, tokens))

	total_tool_tokens = sum(t for _, t in tool_entries)
	if total_tool_tokens <= combined_limit:
		return thread

	# evict oldest tool results first until within budget
	messages = list(thread.messages)
	compacted_count = 0
	for idx, tokens in tool_entries:
		if total_tool_tokens <= combined_limit:
			break
		original_msg = messages[idx]
		if not isinstance(original_msg, SDKToolMessage):
			continue
		# skip already-compacted results
		if original_msg.tool_output == _COMPACTED_NOTICE:
			continue
		messages[idx] = original_msg.model_copy(
			update={"tool_output": _COMPACTED_NOTICE}
		)
		compacted_tokens = estimate_message_tokens(messages[idx])
		total_tool_tokens -= tokens
		total_tool_tokens += compacted_tokens
		compacted_count += 1

	if compacted_count > 0:
		logger.info(
			"layer 2 guard: compacted %d tool results "
			"(combined tokens: %d -> %d, limit: %d)",
			compacted_count,
			sum(t for _, t in tool_entries),
			total_tool_tokens,
			combined_limit,
		)

	return thread.model_copy(update={"messages": messages})
