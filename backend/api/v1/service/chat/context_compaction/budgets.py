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


DEFAULT_PROMPT_OVERHEAD_TOKENS = 300


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


def setting_int(source: object, name: str, default: int) -> int:
	"""read an integer setting with a defensive fallback."""
	value = getattr(source, name, default)
	if isinstance(value, bool):
		return default
	if isinstance(value, int):
		return value
	return default


def setting_float(source: object, name: str, default: float) -> float:
	"""read a numeric setting as float with a defensive fallback."""
	value = getattr(source, name, default)
	if isinstance(value, bool):
		return default
	if isinstance(value, int | float):
		return float(value)
	return default


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


def summary_cluster_token_limit(budget: int) -> int:
	"""choose the maximum raw batch size for one generated summary."""
	return max(512, min(16_000, int(budget * 0.25)))
