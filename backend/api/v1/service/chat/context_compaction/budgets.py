"""budgeting helpers for context compaction."""

from __future__ import annotations

from collections.abc import Sequence

from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.token_estimation import (
	estimate_message_tokens,
	estimate_tool_definitions_tokens,
)
from nokodo_ai.tool import ToolDefinition
from nokodo_ai.utils.tokens import compute_available_budget


def estimate_compaction_message_tokens(message: SDKMessage) -> int:
	"""estimate prompt-side message cost for compaction decisions."""
	if isinstance(message, SDKAssistantMessage) and message.tool_calls:
		return estimate_message_tokens(message.model_copy(update={"usage": None}))
	return estimate_message_tokens(message)


def sum_message_tokens(messages: list[SDKMessage]) -> int:
	"""sum prompt-side token estimates for a message list."""
	return sum(estimate_compaction_message_tokens(message) for message in messages)


def tool_definition_tokens(
	tool_definitions: Sequence[ToolDefinition] | None,
) -> int:
	"""estimate prompt cost for tool definition JSON schemas."""
	return estimate_tool_definitions_tokens(tool_definitions or ())


def effective_context_window(
	context_window: int | None,
	target_usage_cap_tokens: int | None,
) -> int | None:
	"""apply an optional target usage cap to the model context window."""
	if target_usage_cap_tokens is None:
		return context_window
	if context_window is None:
		return target_usage_cap_tokens
	return min(context_window, target_usage_cap_tokens)


def budget_for_system(
	context_window: int | None,
	system_msgs: list[SDKMessage],
	tool_definition_tokens: int,
	prompt_overhead_tokens: int,
	response_headroom: int,
) -> int:
	"""compute remaining conversation budget after fixed prompt costs."""
	return compute_available_budget(
		context_window,
		system_prompt_tokens=(
			sum_message_tokens(system_msgs)
			+ tool_definition_tokens
			+ prompt_overhead_tokens
		),
		response_headroom=response_headroom,
	)


def prompt_tokens(
	system_msgs: list[SDKMessage],
	conversation_tokens: int,
	tool_definition_tokens: int,
	prompt_overhead_tokens: int,
) -> int:
	"""combine fixed and conversation token costs for comparison."""
	return (
		sum_message_tokens(system_msgs)
		+ tool_definition_tokens
		+ prompt_overhead_tokens
		+ conversation_tokens
	)


def trigger_limit(budget: int, trigger_ratio: float) -> int:
	"""convert a budget ratio into a background summary trigger limit."""
	return int(budget * trigger_ratio)


def summary_cluster_token_limit(
	total_tokens: int,
	budget: int,
	recovery_target_ratio: float,
	min_tokens: int,
	max_tokens: int,
) -> int:
	"""choose the raw token target for one generated summary."""
	tokens_to_free = total_tokens - int(budget * recovery_target_ratio)
	if tokens_to_free <= 0:
		return 0
	return max(min_tokens, min(max_tokens, tokens_to_free))
