"""protocol-aware last-resort message pruning."""

from __future__ import annotations

from api.v1.service.chat.context_compaction.budgets import sum_message_tokens
from api.v1.service.chat.context_compaction.protection import protected_indices
from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.utils.typeid import TypeID


def _cluster_bounds_for_prune(
	messages: list[SDKMessage],
	index: int,
) -> tuple[int, int]:
	"""find the protocol-valid cluster containing a candidate message."""
	message = messages[index]
	if isinstance(message, SDKAssistantMessage) and message.tool_calls:
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
		return index, end
	if isinstance(message, SDKToolMessage):
		for start in range(index - 1, -1, -1):
			candidate = messages[start]
			if not isinstance(candidate, SDKAssistantMessage):
				continue
			if any(call.id == message.tool_call_id for call in candidate.tool_calls):
				return _cluster_bounds_for_prune(messages, start)
	return index, index + 1


def prune_oldest_until(
	messages: list[SDKMessage],
	message_ids: list[str | None],
	target_tokens: int,
	run_id: TypeID | None,
	protected_tool_groups: int,
) -> tuple[list[SDKMessage], list[str | None], int, int]:
	"""remove oldest unprotected protocol-valid clusters until budget fits."""
	result = list(messages)
	result_ids = list(message_ids)
	total_tokens = sum_message_tokens(result)
	pruned_count = 0
	while total_tokens > target_tokens and len(result) > 1:
		protected = protected_indices(result, run_id, protected_tool_groups)
		cluster: tuple[int, int] | None = None
		for index in range(len(result)):
			start, end = _cluster_bounds_for_prune(result, index)
			if any(item in protected for item in range(start, end)):
				continue
			cluster = (start, end)
			break
		if cluster is None:
			break
		start, end = cluster
		removed = result[start:end]
		del result[start:end]
		del result_ids[start:end]
		total_tokens -= sum_message_tokens(removed)
		pruned_count += len(removed)
	return result, result_ids, total_tokens, pruned_count
