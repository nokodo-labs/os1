"""tool call and tool output compaction helpers."""

from __future__ import annotations

import logging

from api.settings import settings as app_settings
from api.v1.service.chat.context_compaction.budgets import (
	budget_for_system,
	estimate_compaction_message_tokens,
	sum_message_tokens,
)
from api.v1.service.chat.context_compaction.protection import protected_indices
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import TextContent
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.threads import Thread as SDKThread
from nokodo_ai.utils.tokens import CHARS_PER_TOKEN, SAFETY_MARGIN
from nokodo_ai.utils.typeid import TypeID


logger = logging.getLogger(__name__)

COMPACTED_TOOL_OUTPUT_NOTICE = "[compacted: tool output removed to free context]"
_COMPACTED_TOOL_ARGUMENTS = {
	"_compacted": "tool call arguments removed to free context"
}
_TOOL_OUTPUT_COMPACTION_NOTICE = (
	"\n\n[... truncated: {original_chars} chars total, "
	"{removed_chars} chars removed to fit context budget ...]"
)


def _tool_arguments_are_compactable(arguments: object) -> bool:
	"""return whether tool-call arguments can be replaced by a notice."""
	if not arguments:
		return False
	if isinstance(arguments, dict) and arguments == _COMPACTED_TOOL_ARGUMENTS:
		return False
	return True


def _compact_tool_call_arguments_until(
	messages: list[SDKMessage],
	target_tokens: int,
	protected_indices: set[int] | None = None,
) -> tuple[list[SDKMessage], int, int]:
	"""compact old assistant tool-call arguments before pruning messages."""
	protected = protected_indices or set()
	total_tokens = sum_message_tokens(messages)
	if total_tokens <= target_tokens:
		return messages, total_tokens, 0

	result = list(messages)
	compacted_count = 0

	for index, message in enumerate(result):
		if total_tokens <= target_tokens:
			break
		if index in protected or not isinstance(message, SDKAssistantMessage):
			continue
		if not message.tool_calls:
			continue

		updated_tool_calls = []
		changed = False
		for tool_call in message.tool_calls:
			if _tool_arguments_are_compactable(tool_call.arguments):
				updated_tool_calls.append(
					tool_call.model_copy(
						update={"arguments": dict(_COMPACTED_TOOL_ARGUMENTS)}
					)
				)
				changed = True
				compacted_count += 1
			else:
				updated_tool_calls.append(tool_call)

		if not changed:
			continue

		before_tokens = estimate_compaction_message_tokens(message)
		updated_message = message.model_copy(
			update={"tool_calls": updated_tool_calls, "usage": None}
		)
		after_tokens = estimate_compaction_message_tokens(updated_message)
		if after_tokens >= before_tokens:
			compacted_count -= sum(
				1
				for tool_call in message.tool_calls
				if _tool_arguments_are_compactable(tool_call.arguments)
			)
			continue

		result[index] = updated_message
		total_tokens -= before_tokens - after_tokens

	return result, total_tokens, compacted_count


def _truncate_tool_text(text: str, char_limit: int) -> str:
	"""truncate a tool output while preserving an explicit compaction notice."""
	if len(text) <= char_limit:
		return text
	original_len = len(text)
	notice = _TOOL_OUTPUT_COMPACTION_NOTICE.format(
		original_chars=original_len,
		removed_chars=original_len - char_limit,
	)
	keep = max(char_limit - len(notice), 0)
	return text[:keep] + notice


def _truncate_tool_results_to_cap(
	messages: list[SDKMessage],
	budget_tokens: int,
	protected_indices: set[int] | None = None,
) -> tuple[list[SDKMessage], int, int]:
	"""enforce the per-tool-output cap on unprotected tool messages."""
	protected = protected_indices or set()
	compaction_settings = app_settings.ai.context_compaction
	share_tokens = int(budget_tokens * compaction_settings.tool_result_max_share)
	share_chars = int(share_tokens * CHARS_PER_TOKEN / SAFETY_MARGIN)
	char_limit = max(1, min(share_chars, compaction_settings.tool_result_hard_cap))
	result = list(messages)
	changed_count = 0
	for index, message in enumerate(result):
		if index in protected or not isinstance(message, SDKToolMessage):
			continue
		if (
			not message.tool_output
			or message.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		):
			continue
		truncated = _truncate_tool_text(message.tool_output, char_limit)
		if truncated == message.tool_output:
			continue
		result[index] = message.model_copy(update={"tool_output": truncated})
		changed_count += 1
	return result, sum_message_tokens(result), changed_count


def _compact_combined_tool_outputs(
	messages: list[SDKMessage],
	budget_tokens: int,
	protected_indices: set[int] | None = None,
) -> tuple[list[SDKMessage], int, int]:
	"""compact oldest tool outputs until their combined budget share fits."""
	protected = protected_indices or set()
	combined_limit = int(
		budget_tokens
		* app_settings.ai.context_compaction.tool_results_combined_max_share
	)
	tool_entries: list[tuple[int, int]] = []
	for index, message in enumerate(messages):
		if index in protected or not isinstance(message, SDKToolMessage):
			continue
		if (
			not message.tool_output
			or message.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE
		):
			continue
		tool_entries.append((index, estimate_compaction_message_tokens(message)))

	total_tool_tokens = sum(tokens for _, tokens in tool_entries)
	if total_tool_tokens <= combined_limit:
		return messages, sum_message_tokens(messages), 0

	result = list(messages)
	compacted_count = 0
	for index, tokens in tool_entries:
		if total_tool_tokens <= combined_limit:
			break
		message = result[index]
		if not isinstance(message, SDKToolMessage):
			continue
		updated_message = message.model_copy(
			update={"tool_output": COMPACTED_TOOL_OUTPUT_NOTICE}
		)
		result[index] = updated_message
		total_tool_tokens -= tokens
		total_tool_tokens += estimate_compaction_message_tokens(updated_message)
		compacted_count += 1

	return result, sum_message_tokens(result), compacted_count


def _tool_run_clusters(messages: list[SDKMessage]) -> list[tuple[int, int]]:
	"""find assistant/tool-message runs that must be compacted as units."""
	clusters: list[tuple[int, int]] = []
	index = 0
	while index < len(messages):
		message = messages[index]
		if not isinstance(message, SDKAssistantMessage) or not message.tool_calls:
			index += 1
			continue
		call_ids = {call.id for call in message.tool_calls}
		end = index + 1
		while end < len(messages):
			candidate = messages[end]
			if (
				not isinstance(candidate, SDKToolMessage)
				or candidate.tool_call_id not in call_ids
			):
				break
			end += 1
		if end > index + 1:
			clusters.append((index, end))
		index = end
	return clusters


def _tool_run_summary(messages: list[SDKMessage]) -> str:
	"""build a compact textual notice for one tool-call run."""
	assistant = next(
		(message for message in messages if isinstance(message, SDKAssistantMessage)),
		None,
	)
	tool_names: list[str] = []
	if isinstance(assistant, SDKAssistantMessage):
		tool_names = [call.name for call in assistant.tool_calls]
	outputs: list[str] = []
	for message in messages:
		if isinstance(message, SDKToolMessage) and message.tool_output:
			text = " ".join(message.tool_output.split())
			outputs.append(text[:300])
	joined_outputs = " | ".join(outputs)
	if len(joined_outputs) > 900:
		joined_outputs = joined_outputs[:900] + "..."
	name_text = ", ".join(tool_names) if tool_names else "tool calls"
	if joined_outputs:
		return f"[compacted tool run: {name_text}; outputs: {joined_outputs}]"
	return f"[compacted tool run: {name_text}; outputs removed]"


def _summarize_tool_runs_until(
	messages: list[SDKMessage],
	target_tokens: int,
	protected_indices: set[int] | None = None,
) -> tuple[list[SDKMessage], int, int]:
	"""replace old unprotected tool runs with compact summary notices."""
	protected = protected_indices or set()
	total_tokens = sum_message_tokens(messages)
	if total_tokens <= target_tokens:
		return messages, total_tokens, 0

	result = list(messages)
	compacted_count = 0
	for start, end in _tool_run_clusters(result):
		if total_tokens <= target_tokens:
			break
		if any(index in protected for index in range(start, end)):
			continue
		cluster = result[start:end]
		before_tokens = sum_message_tokens(cluster)
		summary = _tool_run_summary(cluster)
		updated_cluster: list[SDKMessage] = []
		for message in cluster:
			if isinstance(message, SDKAssistantMessage):
				updated_calls = [
					call.model_copy(
						update={"arguments": dict(_COMPACTED_TOOL_ARGUMENTS)}
					)
					for call in message.tool_calls
				]
				updated_cluster.append(
					message.model_copy(
						update={
							"content": [TextContent(text=summary)],
							"tool_calls": updated_calls,
							"usage": None,
						}
					)
				)
			elif isinstance(message, SDKToolMessage):
				updated_cluster.append(
					message.model_copy(
						update={"tool_output": COMPACTED_TOOL_OUTPUT_NOTICE}
					)
				)
			else:
				updated_cluster.append(message)
		after_tokens = sum_message_tokens(updated_cluster)
		if after_tokens >= before_tokens:
			continue
		result[start:end] = updated_cluster
		total_tokens -= before_tokens - after_tokens
		compacted_count += 1

	return result, total_tokens, compacted_count


def apply_tool_io_cascade(
	messages: list[SDKMessage],
	budget_tokens: int,
	run_id: TypeID | None,
	protected_tool_groups: int,
) -> tuple[list[SDKMessage], int, int, int, int]:
	"""run the tier-1 tool I/O cascade over unprotected old tool traffic.

	the cascade owns the ordering from the refactor plan: first compact tool-call
	arguments, then enforce per-output caps, then enforce the combined-output cap,
	then summarize whole tool runs as protocol-safe units. after each stage it
	recomputes protection because earlier rewrites can change the message list's
	shape and token cost.
	"""
	protected = protected_indices(messages, run_id, protected_tool_groups)
	total_tokens = sum_message_tokens(messages)
	tool_call_count = 0
	tool_result_count = 0
	tool_run_count = 0
	working = messages
	if total_tokens > budget_tokens:
		working, total_tokens, count = _compact_tool_call_arguments_until(
			working,
			budget_tokens,
			protected,
		)
		tool_call_count += count
	if total_tokens > budget_tokens:
		protected = protected_indices(working, run_id, protected_tool_groups)
		working, total_tokens, count = _truncate_tool_results_to_cap(
			working,
			budget_tokens,
			protected,
		)
		tool_result_count += count
	if total_tokens > budget_tokens:
		protected = protected_indices(working, run_id, protected_tool_groups)
		working, total_tokens, count = _compact_combined_tool_outputs(
			working,
			budget_tokens,
			protected,
		)
		tool_result_count += count
	if total_tokens > budget_tokens:
		protected = protected_indices(working, run_id, protected_tool_groups)
		working, total_tokens, count = _summarize_tool_runs_until(
			working,
			budget_tokens,
			protected,
		)
		tool_run_count += count
	return working, total_tokens, tool_call_count, tool_result_count, tool_run_count


def enforce_combined_tool_budget(
	thread: SDKThread,
	context_window: int | None,
) -> SDKThread:
	"""enforce a combined token budget across all tool results."""
	compaction_settings = app_settings.ai.context_compaction
	budget = budget_for_system(
		context_window,
		[],
		0,
		0,
		response_headroom=compaction_settings.response_headroom,
	)
	combined_limit = int(budget * compaction_settings.tool_results_combined_max_share)

	tool_entries: list[tuple[int, int]] = []
	for index, message in enumerate(thread.messages):
		if isinstance(message, SDKToolMessage) and message.tool_output:
			tool_entries.append((index, estimate_compaction_message_tokens(message)))

	total_tool_tokens = sum(tokens for _, tokens in tool_entries)
	if total_tool_tokens <= combined_limit:
		return thread

	messages = list(thread.messages)
	compacted_count = 0
	for index, tokens in tool_entries:
		if total_tool_tokens <= combined_limit:
			break
		original_msg = messages[index]
		if not isinstance(original_msg, SDKToolMessage):
			continue
		if original_msg.tool_output == COMPACTED_TOOL_OUTPUT_NOTICE:
			continue
		messages[index] = original_msg.model_copy(
			update={"tool_output": COMPACTED_TOOL_OUTPUT_NOTICE}
		)
		compacted_tokens = estimate_compaction_message_tokens(messages[index])
		total_tool_tokens -= tokens
		total_tool_tokens += compacted_tokens
		compacted_count += 1

	if compacted_count > 0:
		logger.info(
			"layer 2 guard: compacted %d tool results "
			"(combined tokens: %d -> %d, limit: %d)",
			compacted_count,
			sum(tokens for _, tokens in tool_entries),
			total_tool_tokens,
			combined_limit,
		)

	return thread.model_copy(update={"messages": messages})
