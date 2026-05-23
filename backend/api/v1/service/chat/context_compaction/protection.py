"""message protection helpers for context compaction."""

from __future__ import annotations

from nokodo_ai.messages import AssistantMessage as SDKAssistantMessage
from nokodo_ai.messages import Message as SDKMessage
from nokodo_ai.messages import ToolMessage as SDKToolMessage
from nokodo_ai.utils.typeid import TypeID


_RUN_ID_METADATA_KEY = "run_id"
DEFAULT_RECENT_TOOL_PROTECTION_ITERATIONS = 1


def find_run_start_index(
	messages: list[SDKMessage],
	run_id: TypeID | None,
) -> int | None:
	"""find the current run's starting user message index."""
	if run_id is None:
		return None
	run_id_text = str(run_id)
	for index, message in enumerate(messages):
		metadata = message.metadata or {}
		if (
			message.role == "user"
			and str(metadata.get(_RUN_ID_METADATA_KEY)) == run_id_text
		):
			return index
	return None


def _recent_tool_output_indices(
	messages: list[SDKMessage],
	protected_groups: int,
) -> set[int]:
	"""return tail tool-output indices still protected from compaction."""
	if protected_groups <= 0:
		return set()
	protected: set[int] = set()
	index = len(messages) - 1
	while index >= 0 and isinstance(messages[index], SDKToolMessage):
		protected.add(index)
		index -= 1
	return protected


def _tool_call_indices_for_tool_outputs(
	messages: list[SDKMessage],
	tool_indices: set[int],
) -> set[int]:
	"""return assistant tool-call indices paired with protected outputs."""
	protected_call_ids: set[str] = set()
	for index in tool_indices:
		message = messages[index]
		if isinstance(message, SDKToolMessage):
			protected_call_ids.add(message.tool_call_id)
	if not protected_call_ids:
		return set()
	return {
		index
		for index, message in enumerate(messages)
		if isinstance(message, SDKAssistantMessage)
		and any(call.id in protected_call_ids for call in message.tool_calls)
	}


def protected_indices(
	messages: list[SDKMessage],
	run_id: TypeID | None,
	protected_tool_groups: int,
) -> set[int]:
	"""combine run-start and recent tool-output protection indices."""
	protected = _recent_tool_output_indices(messages, protected_tool_groups)
	protected.update(_tool_call_indices_for_tool_outputs(messages, protected))
	run_start_index = find_run_start_index(messages, run_id)
	if run_start_index is not None:
		protected.add(run_start_index)
	return protected
